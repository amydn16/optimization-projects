function [w,b] = NP_ALM(X,Y,alpha,z,tol,maxit)

[nplus, nminus, iplus, iminus] = get_data(Y); % retrieve data

%% Classic augmented Lagrangian method 

beta = 1; % penalty parameter
u = 0; % initialize multiplier for inequality constraint

w = z; % initialize w
b = 0; % initialize b

res = get_res(X,w,b,alpha,nminus,iminus); % get primal residual
dualres = 1; % initialize dual residual

iter_list = []; % list to hold number of outer loop iterations
res_list = []; % list to hold primal residual
dualres_list = []; % list to hold dual residual
outiter = 1; % initialize number of outer loop iterations

fprintf('%s %s %s\n', 'Iterations', 'Primal residual', 'Dual residual');

while ( max(0,res) > tol || dualres > tol ) && outiter < maxit
    
    grad = get_Lwb(X,w,b,alpha,beta,u,nplus,nminus,iplus,iminus); % compute gradient in w
    dualres = norm(grad); % compute violation of dual feasibility in w
    
    % use steepest gradient descent method to find w, b minimizing L
    sigma = sqrt(2); % backtracking constant for inexact line search
    stepsize = 1; % initialize step size
    initer = 0; % initialize number of inner loop iterations
    
    while dualres > tol && initer < maxit
        
        v0 = [w;b]; % store current w, b in a vector
        v = v0 - stepsize*grad; % move from v0 in direction of gradient
        L0 = get_L(X,v0(1:length(v0)-1,:),v0(length(v0)),alpha,beta,u,nplus,nminus,iplus,iminus); % evaluate L at v0
        Lnew = get_L(X,v(1:length(v)-1,:),v(length(v)),alpha,beta,u,nplus,nminus,iplus,iminus); % evaluate L at v
        
         % check that gradient is descent direction
        if Lnew > L0
            stepsize = 1; % reset step size to 1
            while Lnew > L0
                stepsize = stepsize/sigma; % backtrack by factor of sigma
                v = v0 - stepsize*grad; % move from v0 using new step size
                Lnew = get_L(X,v(1:length(v)-1,:),v(length(v)),alpha,beta,u,nplus,nminus,iplus,iminus); % update Lnew
            end
        end
        
        w = v(1:length(v)-1,:); % retrieve new iterate of w
        b = v(length(v)); % retrieve new iterate of b
        
        grad = get_Lwb(X,w,b,alpha,beta,u,nplus,nminus,iplus,iminus); % update gradient
        dualres = norm(grad); % update violation of dual feasibility
        res = get_res(X,w,b,alpha,nminus,iminus); % update primal residual
        initer = initer + 1; % update number of inner loop iterations
    end
    
    u = max(0, u + beta*res); % update multiplier
    
    iter_list = [iter_list; outiter]; % record number of outer loop iterations
    dualres_list = [dualres_list; dualres]; % record dual residual
    res_list = [res_list; res]; % record primal residual
    
    fprintf('%d %5.4e %5.4e \n', outiter, res, dualres);
    
    outiter = outiter + 1; % update number of outer loop iterations
end

n_err = get_nerr(X,w,b,nplus,iplus); % get false negative error
fprintf('False negative error = %5.4e\n', n_err);

p_err = get_perr(X,w,b,nminus,iminus); % get false positive error
fprintf('False positive error = %5.4e\n', p_err);

% plot results for spam data
figure(1)
plot(iter_list,res_list,'r','LineWidth',2);
xlabel('Number of outer loop iterations'); ylabel('Primal residual'); set(gca,'FontSize',12);
figure(2)
semilogy(dualres_list,'b','LineWidth',2);
xlabel('Number of outer loop iterations'); ylabel('Dual residual'); set(gca,'FontSize',12);
end

%% Functions called within algorithm

% define function to get count and indices of positive data
function [nplus, nminus, iplus, iminus] = get_data(Y)

countp = 0; % initialize counter of positive data
countm = 0; % initialize counter of negative data
listp = []; % initialize list of positive indices
listm = []; % initialize list of negative indices

for i = 1:length(Y)
    if Y(i) == 1
        countp = countp + 1; % update counter
        listp = [listp; i]; % add index to list
    else
        countm = countm + 1; % update counter
        listm = [listm; i]; % add index to list
    end
end

nplus = countp; nminus = countm; % return final counts
iplus = listp; iminus = listm; % return index lists
end

% define Lagrangian function
function L = get_L(X,w,b,alpha,beta,u,nplus,nminus,iplus,iminus)

sum_plus = 0; sum_minus = 0; % initialize positive and negative sums

for i = 1:nplus % compute objective value in Lagrangian
    sum_plus = sum_plus + log(1 + exp(-(w'*X(:,iplus(i)) + b)));
end

for i = 1:nminus % compute constraint value in Lagrangian
    sum_minus = sum_minus + log(1 + exp(w'*X(:,iminus(i)) + b));
end
% compute value of Lagrangian
L = sum_plus/nplus + 0.5*beta*max(0, sum_minus/nminus - alpha + ...
    u/beta)^2 - (u^2)/(2*beta);
end

% define objective function
function n_err = get_nerr(X,w,b,nplus,iplus)

sum_plus = 0; % initialize sum
for i = 1:nplus % compute objective value in Lagrangian
    sum_plus = sum_plus + log(1 + exp(-(w'*X(:,iplus(i)) + b)));
end
% compute false negative error
n_err = sum_plus/nplus; 
end

% define constraint function
function p_err = get_perr(X,w,b,nminus,iminus)

sum_minus = 0; % initialize sum
for i = 1:nminus % compute constraint value
    sum_minus = sum_minus + log(1 + exp(w'*X(:,iminus(i)) + b));
end
% compute false positive error
p_err = sum_minus/nminus;
end

% define gradient of Lagrangian with respect to w, b
function Lwb = get_Lwb(X,w,b,alpha,beta,u,nplus,nminus,iplus,iminus)

% initialize positive and negative sums, inequality constraint g
sum_plus = 0; sum_minus = 0; g = 0;

for i = 1:nplus % compute gradient of objective function
    sum_plus = sum_plus - ...
        exp(-(w'*X(:,iplus(i)) + b))*[X(:,iplus(i));1]/(1 + exp(-(w'*X(:,iplus(i)) + b)));
end

for i = 1:nminus % compute gradient of constraint
    g = g + log(1 + exp(w'*X(:,iminus(i)) + b)); % compute inequality
    sum_minus = sum_minus + ...
        exp(w'*X(:,iminus(i)) + b)*[X(:,iminus(i));1]/(1 + exp(w'*X(:,iminus(i)) + b));
end
% compute gradient
Lwb = sum_plus/nplus + beta*max(0, g/nminus - alpha + u/beta)*sum_minus/nminus;
end

% define primal residual
function res = get_res(X,w,b,alpha,nminus,iminus)

sum = 0; % initialize sum

for i = 1:nminus
    sum = sum + log(1 + exp((w'*X(:,iminus(i))) + b));
end
res = sum/nminus - alpha; % compute and return residual
end
