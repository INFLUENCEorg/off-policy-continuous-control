import argparse
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from plot_utils import neighbor_smooth, ignore_hidden_and_png

plt.rc('font', family='serif')

parser = argparse.ArgumentParser()
parser.add_argument('--env', type=str, required=True)
args = parser.parse_args()

env_dir = args.env

for algo_folder in ignore_hidden_and_png(os.listdir(env_dir)):

    run_folders = ignore_hidden_and_png(os.listdir(os.path.join(env_dir, algo_folder)))

    ep_rets_s = []

    for run_folder in run_folders:
        csv_path = os.path.join(env_dir, algo_folder, run_folder, 'progress.csv')

        df = pd.read_csv(csv_path)

        steps = df['timestep'].to_numpy()
        ep_rets = df['test_ep_ret'].to_numpy()
        ep_rets = neighbor_smooth(list(ep_rets), 11)

        ep_rets_s.append(ep_rets)

    ep_rets_s = np.array(ep_rets_s)
    mean_ep_ret = ep_rets_s.mean(axis=0)  # average across all seeds
    std_ep_ret = ep_rets_s.std(axis=0)

    plt.plot(steps, mean_ep_ret, label=f'{algo_folder} ({len(run_folders)} runs)')
    plt.fill_between(steps, mean_ep_ret - std_ep_ret, mean_ep_ret + std_ep_ret, alpha=0.2)

plt.title(args.env)
plt.xlabel('Timestep')
plt.ylabel('Test-time Return')
plt.legend(loc='lower right')

plt.grid()
plt.gca().spines['right'].set_visible(False)
plt.gca().spines['top'].set_visible(False)
plt.ticklabel_format(style='sci', axis='x', scilimits=(0, 0))

plt.savefig(f'{env_dir}/avg_return.png', dpi=200)