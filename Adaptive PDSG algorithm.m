function [x,runtime,outputs] = adaptPDSG(H,c,Q,a,b,x,lb,ub,m,N,params)

t0 = tic; % start cpu timer

outputs = []; % array to hold outputs
outputs.x = []; % array to hold x at each epoch
outputs.f = []; % holds objective function value at each iteration
outputs.favg = []; % holds objective function value at each epoch
outputs.viol = []; % holds average constraint violation at each iteration
outputs.violmax = []; % holds maximum constraint violation at each iteration
outputs.violavg = []; % holds constraint violation at each epoch
outputs.violmaxavg = []; % holds maximum constraint violation at each epoch

maxepoch = params.maxepoch; % maximum number of epochs
maxiter = params.maxiter; % maximum number of iterations per epoch
batchsize = params.batchsize; % size of each minibatch

alpha = params.alpha0/(params.K^0.5); % 1st parameter in update step size for x
beta = params.beta; % penalty parameter
rho = params.rho0/(params.K^0.5); % update parameter for z
eta = 1/(params.batchsize^0.5); % parameter for scaling update step size for x

z = zeros(m,1); % initialize dual variable as nx1 zero vector

for anepoch = 1:maxepoch
  
    xfinal = 0; % initialize x outputted after each epoch
    zfinal = 0; % initialize z outputted after each epoch
    
    gplushsum = 0; % initialize sum of g0 + h at each iteration
    
    for aniter = 0:maxiter
        
        xfinal = xfinal + x; % update xfinal before updating x
        zfinal = zfinal + z; % update zfinal before updating z
        
        f = getf(H,c,x,N); % compute f at x
        outputs.f = [outputs.f f]; % update outputs.f
        
        % randomly select batchsize many integers from [1,m]
        jks = randsample(m,batchsize); 
        
        g0 = 0; % initialize g0temp as 0
        h = 0; % initialize htemp as 0
        
        violbatch = 0; % initialize constraint violation for minibatch
        violmax = 0; % initialize maximum constraint violation for minibatch
   
        for i = 1:batchsize
            jk = jks(i); % get ith element of jks
            
            fjk = getfconstr(Q,a,b,x,jk); % compute f_jk at x
            z(jk) = z(jk) + rho*max(fjk, -z(jk)/beta); % update z_jk
            
            % compute stochastic subgradient of f_0jk at x, update g0
            g0 = g0 + getdfj(H,c,x,jk);
            % compute h_jk at x, update h
            h = h + max(0, beta*fjk + z(jk)) * getdfconstr(Q,a,x,jk);
            
            aviol = getviol(Q,a,b,x,jk); % compute jkth violation at x
            violbatch = violbatch + aviol; % update violbatch
            if (aviol >= violmax) % jkth violation larger than violmax
                violmax = aviol; % update violmax
            end
        end
        
        violbatch = violbatch/batchsize; % average violation for minibatch
        outputs.viol = [outputs.viol violbatch]; % update outputs.viol
        outputs.violmax = [outputs.violmax violmax]; % update outputs.violmax

        gplush = (g0 + h)/batchsize; % averaged sum of g0 and h for this iteration
        % use to scale gplush by norm(g0 + h) if its greater than 1
        gamma = max(1, norm(gplush));
        gplushsum = gplushsum + (gplush.^2)/(gamma^2); % update with square of scaled gplush
        
        fprintf('Epochs: %d, Iterations: %d, f = %8.4e, avg constr viol = %8.4e, max constr viol = %8.4e\n',...
            anepoch, aniter, f, violbatch, violmax);
           
        if (aniter == maxiter)
            break % terminate once algorithm has done maxiter many iterations
        else % execute updates
            
            for i = 1:length(x)
                x(i) = x(i) - gplush(i)/(eta*(gplushsum(i)^0.5) + 1/alpha); % update each x_i
            end
            x = min(ub, max(lb, x)); % projection mapping of x into X
        end
    end
    
    xfinal = xfinal/maxiter; % average x
    x = xfinal; % update x
    outputs.x = [outputs.x xfinal]; % update outputs.x
    
    zfinal = zfinal/maxiter; % average z
    z = zfinal; % update z
    
    f = getf(H,c,x,N); % update f
    outputs.favg = [outputs.favg f]; % update outputs.favg
    
    violmax = 0; % initialize maximum constraint violation after an epoch
    violtot = 0; % intialize constraint violation after an epoch
    
    for i = 1:m
        aviol = getviol(Q,a,b,x,i); % compute ith violation
        violtot = violtot + aviol; % update violtot
       if (aviol >= violmax) % ith violation larger than violmax
            violmax = aviol; % update violmax
        end
    end
    
    violtot = violtot/m; % average violtot
    outputs.violavg = [outputs.violavg violtot]; % update outputs.violavg
    outputs.violmaxavg = [outputs.violmaxavg violmax]; % update outputs.violavgmax

    fprintf('Epochs: %d, f = %8.4e, avg constr viol = %8.4e, max constr viol = %8.4e\n',...
        anepoch, f, violtot, violmax);
    
    runtime = toc(t0); % stop recording time, return
end
end

%% functions to call within algorithm

% objective function f_0 = (sum^{N}_{i=1} ||H_i x - c_i||^2)/2N
function f = getf(H,c,x,N) 
result = 0; % initialize result as 0
for i = 1:N
    result = result + norm(H{i}*x - c{i})^2; % add ||H_i x - c_i||^2
end
f = result/(2*N); % halve result, average it, return
end

% gradient of f_0j: grad(f_0j) = H_i'*(H_i x - c_i)
function dfj = getdfj(H,c,x,j)
dfj = H{j}'*(H{j}*x - c{j}); % compute grad(f_0j), return
end

% gradient of f_0: grad(f_0) = (sum^{N}_{i=1} H_i'*(H_i x - c_i))/N
function df = getdf(H,c,x,N)
result = 0; % initialize result
for i = 1:N
    result = result + getdfj(H,c,x,i); % add H_{i}^T (H_i x - c_i)
end
df = result/N; % average result, return
end

% jth constraint f_j = 0.5*x'*Q_j*x + a_j'*x - b_j
function fconstr = getfconstr(Q,a,b,x,j)
fconstr = 0.5*x'*Q{j}*x + a{j}'*x - b(j); % compute f_j, return
end

% gradient of jth constraint: grad(f_j) = Q_j*x + a_j
function dfconstr = getdfconstr(Q,a,x,j)
dfconstr = Q{j}*x + a{j}; % compute grad(f_j), return
end

% jth constraint violation f_j = 0.5*x'*Q_j*x + a_j'*x - b_j =< 0
function viol = getviol(Q,a,b,x,j)
result = getfconstr(Q,a,b,x,j); % compute f_j
if (result <= 0)
    viol = 0; % f_j =< 0 implies no violation
else
    viol = result; % nonzero violation if f_j > 0
end
end
