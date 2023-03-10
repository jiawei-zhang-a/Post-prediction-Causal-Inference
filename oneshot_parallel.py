import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.experimental import enable_iterative_imputer
from sklearn.impute import IterativeImputer
import random
from sklearn.impute import KNNImputer
from sklearn import linear_model
import matplotlib.pyplot as plt
from sklearn.impute import SimpleImputer
import scipy.stats as stats
import multiprocessing

#load data
X = np.load("/Users/jiaweizhang/research/data/X.npy")
Y = np.load("/Users/jiaweizhang/research/data/Y.npy")
Z = np.load("/Users/jiaweizhang/research/data/Z.npy")
M = np.load("/Users/jiaweizhang/research/data/M.npy")

def split_df(df):
    # Set the proportion of data to be split
    split_proportion = 0.5

    # Set a random seed for reproducibility
    random.seed(23)

    # Get the indices for the split
    indices = df.index.tolist()
    num_rows = len(df)
    split_index = int(num_rows * split_proportion)

    # Shuffle the indices randomly
    random.shuffle(indices)

    # Get the randomly selected rows for each split
    split1_indices = indices[:split_index]
    split2_indices = indices[split_index:]

    # Split the original DataFrame into two separate DataFrames
    df1 = df.loc[split1_indices]
    df2 = df.loc[split2_indices]
    
    return df1,df2

def T(z,y):

    #the Wilcoxon rank sum test
    n = len(z)
    t = 0
    #O(N^2) version
    """
    for n in range(N):
        rank = sum(1 for n_prime in range(N) if Y[n] >= Y[n_prime])
        T += Z[n] * rank
    """

    #O(N*Log(N)) version
    my_list = []
    for i in range(n):
        my_list.append((z[i],y[i]))
    sorted_list = sorted(my_list, key=lambda x: x[1])

    #Calculate
    for i in range(n):
        t += sorted_list[i][0] * (i + 1)
    
    return t

def getT(G, df):
    
    # Get the imputed data Y and indicator Z
    df_imputed = G.transform(df)
    y = df_imputed[:, Z.shape[1] + X.shape[1]:df_imputed.shape[1]]
    z = df_imputed[:, 0]
    
    z_tiled = np.tile(z, 3)

    # Concatenate the tiled versions of Z together
    new_z = np.concatenate((z_tiled,))
    new_y = y.flatten()

    #the Wilcoxon rank sum test
    t = T(new_z,new_y)

    return t

def worker(args):
    Z, X, M, Y_masked, G1, G2, t1_obs, t2_obs, shape, L = args
    t1_sim = np.zeros(L)
    t2_sim = np.zeros(L)

    for l in range(L):
        Z_sim = np.random.binomial(1, 0.5, shape[0]).reshape(-1, 1)
        df_sim = pd.DataFrame(np.concatenate((Z_sim, X, Y_masked), axis=1))
        df1_sim, df2_sim = split_df(df_sim)
        t1_sim[l] = getT(G1, df1_sim)
        t2_sim[l] = getT(G2, df2_sim)
        if l % 100 == 0:
            completeness = l / L * 100  
            print(f"Task is {completeness:.2f}% complete.")

    p1 = np.mean(t1_sim >= t1_obs, axis=0)
    p2 = np.mean(t2_sim >= t2_obs, axis=0)

    return p1, p2

def one_shot_test_parallel(Z, X, M, Y, G1, G2, L=10000, n_jobs=multiprocessing.cpu_count()):
    """
    A one-shot framework for testing H_0.

    Args:
    Z: 2D array of observed treatment indicators
    X: 2D array of observed covariates
    M: 2D array of observed missing indicators
    Y: 2D array of observed values for K outcomes
    G1: a function that takes (Z, X, M, Y_k) as input and returns the imputed value for outcome k
    G2: a function that takes (Z, X, M, Y_k) as input and returns the imputed value for outcome k
    L: number of Monte Carlo simulations (default is 10000)

    Returns:
    p1: 1D array of exact p-values for testing Fisher's sharp null in part 1
    p2: 1D array of exact p-values for testing Fisher's sharp null in part 2
    """
    #print train start
    print("Training start")

    # create data a whole data frame
    Y_masked = np.ma.masked_array(Y, mask=M)
    Y_masked = Y_masked.filled(np.nan)
    df = pd.DataFrame(np.concatenate((Z, X, Y_masked), axis=1))
    
    # randomly split the data into two parts
    df1, df2 = split_df(df)

    # impute the missing values and calculate the observed test statistics in part 1
    G1.fit(df1)
    t1_obs = getT(G1, df1)

    # impute the miassing values and calculate the observed test statistics in part 2
    G2.fit(df2)
    t2_obs = getT(G2, df2)

    #print train end
    print("Training end")
    
    # print the number of cores
    print(f"Number of cores: {n_jobs}")


    # simulate data and calculate test statistics in parallel
    args_list = [(Z, X, M, Y_masked, G1, G2, t1_obs, t2_obs, df.shape, int(L / n_jobs + 1))] * n_jobs
    with multiprocessing.Pool(processes=n_jobs) as pool:
        p_list = pool.map(worker, args_list)
    p1 = np.mean([p[0] for p in p_list], axis=0)
    p2 = np.mean([p[1] for p in p_list], axis=0)
    
    return p1, p2


if __name__ == '__main__':
    multiprocessing.freeze_support()
    #test MissForest
    missForest = IterativeImputer(estimator = RandomForestRegressor(),max_iter=10, random_state=0)
    p1, p2 = one_shot_test_parallel(Z, X, M, Y, L = 100,G1=missForest, G2=missForest)
    print("p-values for part 1:", p1)
    print("p-values for part 2:", p2)

    #test KNNimputer
    KNNimputer = KNNImputer(n_neighbors=2)
    p1, p2 = one_shot_test_parallel(Z, X, M, Y, G1=KNNimputer, G2=KNNimputer)
    print("p-values for part 1:", p1)
    print("p-values for part 2:", p2)

    #test BayesianRidge
    BayesianRidge = IterativeImputer(estimator = linear_model.BayesianRidge(),max_iter=10, random_state=0)
    p1, p2 = one_shot_test_parallel(Z, X, M, Y, G1=BayesianRidge, G2=BayesianRidge)
    print("p-values for part 1:", p1)
    print("p-values for part 2:", p2)

    #test Median imputer
    median_imputer = SimpleImputer(missing_values=np.nan, strategy='median')
    p1, p2 = one_shot_test_parallel(Z, X, M, Y, G1=median_imputer, G2=median_imputer)
    print("p-values for part 1:", p1)
    print("p-values for part 2:", p2)
    