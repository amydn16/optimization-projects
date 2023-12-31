from __future__ import print_function
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
import pandas as pd

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



class LeNet5_smooth(nn.Module):
    def __init__(self):
        super(LeNet5_smooth, self).__init__()
        self.conv1 = nn.Conv2d(1, 6, 5, 1)
        self.conv2 = nn.Conv2d(6, 16, 5, 1)
        self.fc1 = nn.Linear(256, 120)
        self.fc2 = nn.Linear(120,84)
        self.fc3 = nn.Linear(84,10)

    def forward(self, x):
        x = F.tanh(self.conv1(x))
        x = F.max_pool2d(x, 2, 2)
        x = F.tanh(self.conv2(x))
        x = F.max_pool2d(x, 2, 2)
        x = x.view(-1, 256)
        x = F.tanh(self.fc1(x))
        x = F.tanh(self.fc2(x))
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


def train(args, model, device, train_loader, optimizer, epoch, lr,\
          gradlist, updatelist, outputlist, iter, opttype):
    model.train()
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        output = model(data)
        loss = F.nll_loss(output, target)
        loss.backward()

        # Hybrid-SGD
        if opttype == 'Hybrid-SGD':
            
            def aclosure(): # Get gradients from separate sample
                optimizer.zero_grad()
                output = model(data)
                loss = F.nll_loss(output, target)
                loss.backward()
                othergrad = []
                for p in model.parameters(): # Store gradients in list
                    othergrad = othergrad + [p.grad]
                return othergrad
            othergrad = aclosure()
            
            L = 2 # Approximate Lipschitz constant
            B0 = args.batch_size**0.5
            gamma = 0.95
            eta = 0.25
            beta = 1 - 1/((B0*(iter + 1))**0.5)
            player = 0 # Counter to keep track of layer in network
            for p in model.parameters():
                if iter == 1: # Store gradient and x at this iteration
                    gradlist = grad_list(gradlist, p.grad, player)
                    outputlist = output_list(outputlist, p.data, player)
                    p.grad.mul_(1/B0) # Store v at this iteration
                    updatelist = update_list(updatelist, p.grad, player)
                    p.grad.mul_(-eta)
                    p.data.add_(p.grad) # Update x
                else: # Get gradient and v at previous iteration
                    v0 = updatelist[player][-1].clone()
                    grad0 = gradlist[player][-1].clone()
                    gradlist = grad_list(gradlist, p.grad, player) 
                    v0.mul_(beta)
                    grad0.mul_(beta)
                    anothergrad = othergrad[player].clone()
                    anothergrad.mul_(1 - beta)
                    p.grad.mul_(beta)
                    p.grad.add_(v0 - grad0)
                    updatelist = update_list(updatelist, p.grad, player)
                    p.grad.mul_(-eta)
                    p.data.add_(p.grad) # Update x

                # Proximal mapping of (x - eta*gradient) onto eta*r    
                temp_tensor = p.data.clone()
                top_tensor = temp_tensor[temp_tensor > lr*eta]
                mid_tensor = temp_tensor[temp_tensor.abs() <= lr*eta]
                low_tensor = temp_tensor[temp_tensor < -lr*eta]
                top_tensor.add_(-lr*eta)
                mid_tensor = 0
                low_tensor.add_(lr*eta)
                p.data[p.data > lr*eta] = top_tensor
                p.data[p.data.abs() <= lr*eta] = mid_tensor
                p.data[p.data < -lr*eta] = low_tensor

                # Add (1 - gamma)*(x at previous iteration) to mapping
                p.data.mul_(gamma)
                old_tensor = outputlist[player][-1].clone() # x at previous iteration
                old_tensor.mul_(1 - gamma)
                p.data.add_(old_tensor) # Update x
                outputlist = output_list(outputlist, p.data, player)    
                player += 1 # Update layer counter before moving onto next layer

        # SpiderBoost
        elif opttype == 'SpiderBoost':
            L = 2
            eta = 1/(2*L)
            S = args.batch_size**0.5
            player = 0
            for p in model.parameters():
                if iter == 1:
                    gradlist = grad_list(gradlist, p.grad, player)
                    p.grad.mul_(1/S)
                    updatelist = update_list(updatelist, p.grad, player)
                    p.grad.mul(-eta)
                    p.data.add_(p.grad)
                else:
                    grad0 = gradlist[player][-1].clone()
                    v0 = updatelist[player][-1].clone()
                    gradlist = grad_list(gradlist, p.grad, player)
                    p.grad.add_(v0 - grad0)
                    p.grad.mul_(1/S)
                    updatelist = update_list(updatelist, p.grad, player)
                    p.grad.mul_(-eta)
                    p.data.add_(p.grad)
    
                temp_tensor = p.data.clone()
                top_tensor = temp_tensor[temp_tensor > lr*eta]
                mid_tensor = temp_tensor[temp_tensor.abs() <= lr*eta]
                low_tensor = temp_tensor[temp_tensor < -lr*eta]
                top_tensor.add_(-lr*eta)
                mid_tensor = 0
                low_tensor.add_(lr*eta)
                p.data[p.data > lr*eta] = top_tensor
                p.data[p.data.abs() <= lr*eta] = mid_tensor
                p.data[p.data < -lr*eta] = low_tensor
                player += 1

        # PStorm
        elif opttype == 'PStorm':
            B0 = args.batch_size**0.5
            L = 2
            eta0 = (4**1/3)/(8*L)
            eta = eta0/((iter + 4)**(1/3))
            eta1 = eta0/((iter + 4 + 1)**(1/3))
            beta = (1 + (20*(eta*L)**2) - (eta1/eta))/(1 + 4*(eta*iter)**2)
            player = 0
            for p in model.parameters():
                if iter == 1:
                    gradlist = grad_list(gradlist, p.grad, player)
                    p.grad.mul_(1/B0)
                    updatelist = update_list(updatelist, p.grad, player)
                    p.grad.mul_(-eta)
                    p.data.add_(p.grad)
                else:
                    grad0 = gradlist[player][-1].clone()
                    d0 = updatelist[player][-1].clone()
                    grad0.mul_((1 - beta)/B0)
                    d0.mul_(1 - beta)
                    gradlist = grad_list(gradlist, p.grad, player)
                    p.grad.mul_(1/B0)
                    p.grad.add_(d0 - grad0)
                    updatelist = update_list(updatelist, p.grad, player)
                    p.grad.mul_(-eta)
                    p.data.add_(p.grad)
                    
                temp_tensor = p.data.clone()
                top_tensor = temp_tensor[temp_tensor > lr*eta]
                mid_tensor = temp_tensor[temp_tensor.abs() <= lr*eta]
                low_tensor = temp_tensor[temp_tensor < -lr*eta]
                top_tensor.add_(-lr*eta)
                mid_tensor = 0
                low_tensor.add_(lr*eta)
                p.data[p.data > lr*eta] = top_tensor
                p.data[p.data.abs() <= lr*eta] = mid_tensor
                p.data[p.data < -lr*eta] = low_tensor
                player += 1

        # Vanilla SGD
        elif opttype == 'Vanilla-SGD':
            alpha0 = 1
            for p in model.parameters():        
                p.grad.mul_(-alpha0/(iter**0.5))
                p.data.add_(p.grad)

            temp_tensor = p.data.clone()
            top_tensor = temp_tensor[temp_tensor > lr*alpha0]
            mid_tensor = temp_tensor[temp_tensor.abs() <= lr*alpha0]
            low_tensor = temp_tensor[temp_tensor < -lr*alpha0]
            top_tensor.add_(-lr*alpha0)
            mid_tensor = 0
            low_tensor.add_(lr*alpha0)
            p.data[p.data > lr*alpha0] = top_tensor
            p.data[p.data.abs() <= lr*alpha0] = mid_tensor
            p.data[p.data < -lr*alpha0] = low_tensor

        # Violation of stationarity
        viol = 0
        for param in model.parameters():
            if lr == 0: # Violation = norm(grad) 
                viol += torch.norm(param.grad) # Sum over each layer
            else: # Violation = norm((proximal mapping of (x - grad) onto r) - x)
                themap = param.data - param.grad # x - grad
                temp_map = themap.clone()
                # Compute proximal mapping of (x - grad) onto r
                top_tensor = temp_map[temp_map > lr]
                mid_tensor = temp_map[temp_map.abs() <= lr]
                low_tensor = temp_map[temp_map < -lr]
                top_tensor.add_(-lr)
                mid_tensor = 0
                low_tensor.add_(lr)
                temp_map[temp_map > lr] = top_tensor
                temp_map[temp_map.abs() <= lr] = mid_tensor
                temp_map[temp_map < -lr] = low_tensor 
                viol += torch.norm(temp_map - param.data) # Sum over each layer        
        
        optimizer.zero_grad()        
        iter += 1

        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {}, Violation: {:.6f}, [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, viol, batch_idx * len(data), len(train_loader.dataset),
                100. * batch_idx / len(train_loader), loss.item()))

        if batch_idx*len(data) >= 57600:
            return viol.item() # Return final violation of epoch


# Each nested list holds gradients over all iterations at each layer
def grad_list(alist, agrad, alayer): 
    alist[alayer] = alist[alayer] + [agrad]
    return alist


# Each nested list holds update directions over all iterations at each layer
def update_list(alist, anupdate, alayer):
    alist[alayer] = alist[alayer] + [anupdate]
    return alist


# Each nested list holds x over all iterations at each layer
def output_list(alist, anoutput, alayer):
    alist[alayer] = alist[alayer] + [anoutput]
    return alist


def test(args, model, device, test_loader):
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += F.nll_loss(output, target, reduction='sum').item() # sum up batch loss
            pred = output.argmax(dim=1, keepdim=True) # get the index of the max log-probability
            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader.dataset)

    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, len(test_loader.dataset),
        100. * correct / len(test_loader.dataset)))

    # Return average loss and testing accuracy during each epoch
    return(test_loss, 100. * correct / len(test_loader.dataset))


def main(opttype, lr): # pass in optimization algorithm and learning rate
    # Training settings

    parser = argparse.ArgumentParser(description='MNIST Example')
    parser.add_argument('--batch-size', type=int, default=64, metavar='N', \
                        help='input batch size for training (default: 64)')
    parser.add_argument('--test-batch-size', type=int, default=1000, metavar='N', \
                        help='input batch size for testing (default: 1000)')
    parser.add_argument('--epochs', type=int, default=75, metavar='N', \
                        help='number of epochs to train (default: 50 or 75)')
    parser.add_argument('--seed', type=int, default=20200930, metavar='N', \
                        help='random seed (default: 20200930)')
    parser.add_argument('--log-interval', type=int, default=200, metavar='N', \
                        help='how many batches to wait before logging training status')
    parser.add_argument('--save-model', action='store_true', default=False, \
                        help='for saving the current model')
    args = parser.parse_args()
    
    use_cuda = False

    torch.manual_seed(args.seed)

    device = torch.device("cuda" if use_cuda else "cpu")

    kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}
    train_loader = torch.utils.data.DataLoader(
        datasets.FashionMNIST('data', train=True, download=True,
                       transform=transforms.Compose([
                           transforms.ToTensor(),
                           transforms.Normalize((0.1307,), (0.3081,))
                       ])),
        batch_size=args.batch_size, shuffle=True, **kwargs)
    test_loader = torch.utils.data.DataLoader(
        datasets.FashionMNIST('data', train=False, transform=transforms.Compose([
                           transforms.ToTensor(),
                           transforms.Normalize((0.1307,), (0.3081,))
                       ])),
        batch_size=args.test_batch_size, shuffle=True, **kwargs)
    
    model = LeNet5_smooth().to(device)

    optimizer = optim.SGD(model.parameters(), lr)

    # Initialize lists to store data
    gradlist = [[], [], [], [], [], [], [],[],[],[]]
    updatelist = [[], [], [], [], [], [], [],[],[],[]]
    outputlist = [[], [], [], [], [], [], [],[],[],[]]
    violist = []
    losslist = []
    acclist = []
    
    iter = 1

    # Store violation, average test loss, testing acccuracy at each epoch
    for epoch in range(args.epochs + 1):
        violist = violist + \
        [train(args, model, device, train_loader, optimizer, epoch, lr,\
              gradlist, updatelist, outputlist, iter, opttype)]
        aloss, anacc = test(args, model, device, test_loader)
        losslist = losslist + [aloss]
        acclist = acclist + [anacc]
        iter += 60000//args.batch_size
    return (losslist, acclist, violist) # Return lists
        
if __name__ == '__main__':
    # Labels for results
    labels_sb = ['sb_l', 'sb_a', 'sb_v']
    labels_ps = ['ps_l', 'ps_a', 'ps_v']
    labels_hsgd = ['hsgd_l', 'hsgd_a', 'hsgd_v']
    labels_vsgd = ['vsgd_l', 'vsgd_a', 'vsgd_v']

    # Get results from all 4 algorithms at lr = 1e-4
    loss_sb, acc_sb, viol_sb = main('SpiderBoost', 1e-4)
    results = [loss_sb, acc_sb, viol_sb]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_sb[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '1e-4' + 'sb.csv'
    df.to_csv(filename)

    loss_ps, acc_ps, viol_ps = main('PStorm', 1e-4)
    results = [loss_ps, acc_ps, viol_ps]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_ps[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '1e-4' + 'ps.csv'
    df.to_csv(filename)
    
    loss_hsgd, acc_hsgd, viol_hsgd = main('Hybrid-SGD', 1e-4)
    results = [loss_hsgd, acc_hsgd, viol_hsgd]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_hsgd[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '1e-4' + 'hsgd.csv'
    df.to_csv(filename)

    loss_vsgd, acc_vsgd, viol_vsgd = main('Vanilla-SGD', 1e-4)
    results = [loss_vsgd, acc_vsgd, viol_vsgd]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_vsgd[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '1e-4' + 'vsgd.csv'
    df.to_csv(filename)
    
    # Get results from all 4 algorithms at lr = 1e-6
    loss_sb, acc_sb, viol_sb = main('SpiderBoost', 1e-6)
    results = [loss_sb, acc_sb, viol_sb]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_sb[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '1e-6' + 'sb.csv'
    df.to_csv(filename)

    loss_ps, acc_ps, viol_ps = main('PStorm', 1e-6)
    results = [loss_ps, acc_ps, viol_ps]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_ps[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '1e-6' + 'ps.csv'
    df.to_csv(filename)
    
    loss_hsgd, acc_hsgd, viol_hsgd = main('Hybrid-SGD', 1e-6)
    results = [loss_hsgd, acc_hsgd, viol_hsgd]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_hsgd[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '1e-6' + 'hsgd.csv'
    df.to_csv(filename)

    loss_vsgd, acc_vsgd, viol_vsgd = main('Vanilla-SGD', 1e-6)
    results = [loss_vsgd, acc_vsgd, viol_vsgd]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_vsgd[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '1e-6' + 'vsgd.csv'
    df.to_csv(filename)                        


    # Get results from all 4 algorithms at lr = 0
    loss_sb, acc_sb, viol_sb = main('SpiderBoost', 0)
    results = [loss_sb, acc_sb, viol_sb]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_sb[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '0' + 'sb.csv'
    df.to_csv(filename)

    loss_ps, acc_ps, viol_ps = main('PStorm', 0)
    results = [loss_ps, acc_ps, viol_ps]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_ps[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '0' + 'ps.csv'
    df.to_csv(filename)
    
    loss_hsgd, acc_hsgd, viol_hsgd = main('Hybrid-SGD', 0)
    results = [loss_hsgd, acc_hsgd, viol_hsgd]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_hsgd[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '0' + 'hsgd.csv'
    df.to_csv(filename)

    loss_vsgd, acc_vsgd, viol_vsgd = main('Vanilla-SGD', 0)
    results = [loss_vsgd, acc_vsgd, viol_vsgd]
    thedict = {}
    for i in range(0, len(results)):
        theresult = results[i]
        thedict[labels_vsgd[i]] = [str(item) for item in theresult]
    df = pd.DataFrame(thedict)
    filename = '0' + 'vsgd.csv'
    df.to_csv(filename)
