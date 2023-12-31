from __future__ import print_function
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy.random as random
import numpy as np
import copy
from torchvision import datasets, transforms

class LeNet5(nn.Module):

    def __init__(self):
        super(LeNet5, self).__init__()
        self.conv1 = nn.Conv2d(1, 6, 5, 1)
        self.conv2 = nn.Conv2d(6, 16, 5, 1)
        self.fc1 = nn.Linear(256, 120)
        self.fc2 = nn.Linear(120,84)
        self.fc3 = nn.Linear(84,10)


    def forward(self, x):
        x = F.relu(self.conv1(x))
        x = F.max_pool2d(x, 2, 2)
        x = F.relu(self.conv2(x))
        x = F.max_pool2d(x, 2, 2)
        x = x.view(-1, 256)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return F.log_softmax(x, dim=1)
        
class Net_FC(nn.Module):
    def __init__(self):
        super(Net_FC, self).__init__()
        self.fc1 = nn.Linear(784, 500)
        self.fc2 = nn.Linear(500, 10)
        
    def forward(self, x):
        x = x.view(-1, 784)
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)
        
def get_indices(dataset,class_name):
    indices =  []
    for i in range(len(dataset.targets)):
        if dataset.targets[i] == class_name:
            indices.append(i)
    return indices

## functions for b-bit quantization
def quantmap(maprange,x): # function to randomly map x to maprange
    # get index of element in maprange closest to and larger than x
    idx = np.searchsorted(maprange, x, side='right')
 
    if idx < len(maprange) - 1: # have not reached the end of maprange yet
    # compute probability that x is mapped to element in maprange <= x    
        prob = float((x - maprange[idx-1])/(maprange[idx] - maprange[idx-1]))
        # map x to y
        y = np.random.choice([maprange[idx-1],maprange[idx]], p=[1-prob,prob])
        return y

    else: # at the right endpoint of maprange
        return x # x is unchanged

def quantize2(atensor,b): # b-bit quantization operator for vector and tensor
    shape = list(atensor.size()) # get shape of atensor
    
    themin = float(atensor.min())
    themax = float(atensor.max()) 
    maprange = [themin + i*((themax - themin)/((2**b)-1)) for i in range(0,2**b)]
    
    alist = atensor.flatten().tolist()
    alist = [quantmap(maprange,item) for item in alist]
    alist = np.array(alist, dtype=np.float32)
    alist = np.reshape(alist, shape) # reshape alist into the same shape as atensor

    atensor = torch.from_numpy(alist)
    return atensor


def test(model, device, Xtest, ytest, b_sz):
    model.eval()
    test_loss = 0
    correct = 0
    t_sz = len(ytest)
    num_b = t_sz//b_sz
    with torch.no_grad():
        for i in range(num_b):
            data = Xtest[b_sz*i : b_sz*(i+1), ]
            target = ytest[b_sz*i : b_sz*(i+1), ]
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += F.nll_loss(output, target, reduction='sum').item() # sum up batch loss
            pred = output.argmax(dim=1, keepdim=True) # get the index of the max log-probability
            correct += pred.eq(target.view_as(pred)).sum().item()
            

    test_loss /= t_sz

    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, t_sz,
        100. * correct / t_sz))

def main():
    # Training settings
    use_cuda = False
    device = torch.device("cuda" if use_cuda else "cpu")
    torch.manual_seed(20200930)
     
    dataset_train = datasets.FashionMNIST('data', train=True, download=True,
                        transform=transforms.Compose([
                        transforms.ToTensor(),
                        transforms.Normalize((0.1307,), (0.3081,))
                        ]))
                        
    dataset_test = datasets.FashionMNIST('data', train=False, transform=transforms.Compose([
                           transforms.ToTensor(),
                           transforms.Normalize((0.1307,), (0.3081,))
                       ]))
    
    Xtrain = dataset_train.data.float()
    Xtrain.mul_(1./255.)
    Xtrain.add_(-0.1307)
    Xtrain.mul_(0.3081)

    ytrain = dataset_train.targets
    
    Xtest = dataset_test.data.float()
    Xtest.mul_(1./255.)
    Xtest.add_(-0.1307)
    Xtest.mul_(0.3081)

    ytest = dataset_test.targets
    
    local_Xtrain = []
    local_ytrain = []
    
    for i in range(10):
    
        idx = get_indices(dataset_train, i)
        local_Xtrain.append(Xtrain[idx,])
        local_ytrain.append(ytrain[idx,])
        
    
    b_sz = 10 # batch_size on each local server
    
    b_sz_test = 1000
    
    
    model = Net_FC().to(device)
    
    num_neurons = []
    
    for idx, p in enumerate(model.parameters()):
        num_neurons.append(p.data.size())
    
    
    num_layer = len(num_neurons)
    
    lr = 1e-2
    b = 4
    
    optimizer = optim.SGD(model.parameters(), lr=lr)
    
    
    iter = 1
    alpha0 = 1
    
    iter_per_epoch = 60000//(10*b_sz)
    maxepoch = 10

    errloc = []
    errcen = []
    gradloc = []
    for layer in range(num_layer):
        gradloc.append(torch.zeros(num_neurons[layer]))
        errloc += [[]]
        errcen += [[]]
    
    for epoch in range(maxepoch):
        for k in range(iter_per_epoch):
            for i in range(10):
                st_idx = random.randint(0, 6000 - b_sz + 1)
                data = local_Xtrain[i][st_idx:st_idx+b_sz,]
                target = local_ytrain[i][st_idx:st_idx+b_sz,]
                data, target = data.to(device), target.to(device)
                optimizer.zero_grad()
                output = model(data)
                loss = F.nll_loss(output, target)
                loss.backward()
                        
                # now the stochastic gradient is computed by the i-th dataset
                # compress the gradient (with error compensation) and send to the central server
                player = 0 # counter to keep track of layers            
                for p in model.parameters():
                    gradclone = p.grad.data.clone() # clone gradient

                    if k == 0: # quantize gradclone
                        gradclone = quantize2(gradclone,b)

                    else:
                        # add last compression error to gradclone before compressing
                        gradclone.add_(errloc[player][-1])
                        gradclone = quantize2(gradclone,b)
                    
                    # aggregate compressed gradient
                    gradloc[player].add_(gradclone)
                    gradclone.mul_(-1) 
                    p.grad.add_(gradclone) # compute local compression error
                    errloc[player] += [p.grad] # store compression error
                    player += 1 # update layer counter

                
                        
            # the central server receives all compressed stochastic gradients
            # average them, then compress the averaged gradient with error compensation, and broadcast to local servers
            
            gradcen = [] # list to store gradients for central server
            for i in range(0,len(gradloc)):
                agrad = torch.Tensor(gradloc[i]) # ensure gradient is tensor
                agrad.mul_(0.1) # average each gradient
                gradcen += [agrad] # store agrad in gradcen

            player = 0
            for p in model.parameters(): # access global model
                v = gradcen[player].clone() # get gradient for this layer
                vclone = v.clone() # clone v
                
                if k == 0: # compress v
                    v = quantize2(v,b)
                else:
                    # add last compression error to gradient before compressing
                    v.add_(errcen[player][-1])
                    v = quantize2(v,b)

                v.mul_(-1)
                vclone.add_(v) # central compression error
                errcen[player] = [vclone] # store compression error
                v.mul_(alpha0*lr/(iter**0.5)) # use smaller step size than for vanilla SGD
                p.data.add_(v) # update global model
                player += 1
                
            print(k)
            iter += 1
            
            if k % 10 == 0:
                print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                    epoch, k * b_sz * 10, 60000,
                    100. * k * b_sz * 10 / 60000, loss.item()))
                    
        test(model, device, Xtest, ytest, b_sz_test)

        
if __name__ == '__main__':
    main()
