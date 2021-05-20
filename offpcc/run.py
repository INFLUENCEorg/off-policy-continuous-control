import gin
import argparse
import wandb
import os

import gym
from domains import *  # import all non-official environments
from gym.wrappers import RescaleAction

from basics.replay_buffer import ReplayBuffer
from algorithms import *

from basics.run_utils import train, make_log_dir, visualize_trained_policy

algo_name2class = {
    'ddpg': DDPG,
    'td3': TD3,
    'sac': SAC
}

parser = argparse.ArgumentParser()
parser.add_argument('--env', type=str, required=True)
parser.add_argument('--algo', type=str, required=True, help='Choose among "ddpg", "td3" and "sac"')
parser.add_argument('--run_id', nargs='+', type=int, required=True)
parser.add_argument('--config', type=str, required=True, help='Task-specific hyperparameters')
parser.add_argument('--visualize', action='store_true', help='Visualize a trained policy (no training happens)')  # default is false

args = parser.parse_args()

gin.parse_config_file(args.config)

for run_id in args.run_id:  # args.run_id is a list of ints; could contain more than one run_ids

    def env_fn():
        """Any wrapper by default copies the observation and action space of its wrappee."""
        return RescaleAction(gym.make(args.env), -1, 1)

    algorithm = algo_name2class[args.algo](
        input_dim=env_fn().observation_space.shape[0],
        action_dim=env_fn().action_space.shape[0],
    )

    if args.visualize:

        visualize_trained_policy(
            env_fn=env_fn,
            algorithm=algorithm,
            log_dir=make_log_dir(args.env, args.algo, run_id),  # trained model will be loaded from here
            num_videos=1  # number of episodes to record
        )

    else:

        wandb.init(
            project=os.getenv('OFFPCC_WANDB_PROJECT'),
            entity=os.getenv('OFFPCC_WANDB_ENTITY'),
            group=f"{args.env} {args.algo}",
            settings=wandb.Settings(_disable_stats=True),
            name=f'run_id={run_id}'
        )

        buffer = ReplayBuffer()

        train(
            env_fn=env_fn,
            algorithm=algorithm,
            buffer=buffer
        )