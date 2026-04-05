"""
Train Q-learning agent on a gridworld environment.
Usage: python train.py [--env small|medium|large|maze|windy|stochastic|multi_goal]
"""

import argparse
import numpy as np
import os

from qlearning import make_env, QLearningAgent, train, evaluate


ENV_EPISODE_DEFAULTS = {
    "small": 3000,
    "medium": 10000,
    "large": 50000,
    "maze": 15000,
    "windy": 10000,
    "stochastic": 10000,
    "multi_goal": 15000,
}

AGENT_DEFAULTS = {
    "lr": 0.1,
    "gamma": 0.99,
    "eps_start": 1.0,
    "eps_end": 0.01,
    "eps_decay": 0.9995,
    "double_q": False,
    "init_val": 0.0,
}


def main():
    parser = argparse.ArgumentParser(description="Train Q-learning on a gridworld.")
    parser.add_argument("--env", default="small",
                        choices=list(ENV_EPISODE_DEFAULTS.keys()))
    parser.add_argument("--episodes", type=int, default=None)
    parser.add_argument("--lr", type=float, default=AGENT_DEFAULTS["lr"])
    parser.add_argument("--gamma", type=float, default=AGENT_DEFAULTS["gamma"])
    parser.add_argument("--eps_decay", type=float, default=AGENT_DEFAULTS["eps_decay"])
    parser.add_argument("--double_q", action="store_true", help="Use Double Q-learning.")
    parser.add_argument("--optimistic_init", type=float, default=0.0,
                        help="Optimistic Q initialization value (e.g. 1.0).")
    parser.add_argument("--slip_prob", type=float, default=0.0,
                        help="Stochastic transition probability.")
    parser.add_argument("--eval_every", type=int, default=None)
    parser.add_argument("--eval_episodes", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--checkpoint", default="agent.pkl")
    parser.add_argument("--render", action="store_true", help="Print final policy grid.")
    args = parser.parse_args()

    env_kwargs = {}
    if args.slip_prob > 0:
        env_kwargs["slip_prob"] = args.slip_prob

    env = make_env(args.env, **env_kwargs)

    n_episodes = args.episodes or ENV_EPISODE_DEFAULTS[args.env]
    eval_every = args.eval_every or max(500, n_episodes // 10)

    print(f"Environment : {args.env}  ({env.rows}x{env.cols})")
    print(f"States      : {env.n_states}")
    print(f"Episodes    : {n_episodes}")
    print(f"Double Q    : {args.double_q}")
    print(f"Slip prob   : {env.slip_prob}")
    print()

    agent = QLearningAgent(
        n_states=env.n_states,
        lr=args.lr,
        gamma=args.gamma,
        eps_start=1.0,
        eps_end=0.01,
        eps_decay=args.eps_decay,
        double_q=args.double_q,
        init_val=args.optimistic_init,
        seed=args.seed,
    )

    history = train(
        env, agent,
        n_episodes=n_episodes,
        eval_every=eval_every,
        eval_episodes=args.eval_episodes,
        verbose=True,
    )

    final_eval = evaluate(env, agent, n_episodes=200)
    print(f"\nFinal greedy eval (200 episodes): mean return = {final_eval:.4f}")

    agent.save(args.checkpoint)
    print(f"Agent saved to {args.checkpoint}")

    if args.render:
        policy = agent.greedy_policy()
        print("\nGreedy policy (^ v < > = directions):\n")
        print(env.render(policy=policy))

    # Plot
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(14, 4))

        window = max(1, n_episodes // 100)
        returns = np.array(history["episode_returns"])
        smoothed = np.convolve(returns, np.ones(window) / window, mode="valid")
        axes[0].plot(smoothed)
        axes[0].set_title(f"Training return (smoothed, w={window})")
        axes[0].set_xlabel("Episode")

        axes[1].plot(history["eval_episodes"], history["eval_returns"])
        axes[1].set_title("Eval return (greedy policy)")
        axes[1].set_xlabel("Episode")

        axes[2].plot(history["epsilons"])
        axes[2].set_title("Epsilon decay")
        axes[2].set_xlabel("Episode")

        plt.tight_layout()
        plt.savefig("qlearning_history.png")
        print("Plot saved to qlearning_history.png")
    except ImportError:
        pass

    # Value function heatmap
    try:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors

        V = agent.Q.max(axis=1).reshape(env.rows, env.cols)
        fig, ax = plt.subplots(figsize=(max(6, env.cols), max(4, env.rows)))
        im = ax.imshow(V, cmap="RdYlGn", aspect="auto")
        plt.colorbar(im, ax=ax, label="V(s) = max_a Q(s,a)")
        ax.set_title(f"Value function - {args.env} grid")

        # Overlay walls and goals
        for r in range(env.rows):
            for c in range(env.cols):
                if (r, c) in env.walls:
                    ax.add_patch(plt.Rectangle((c - 0.5, r - 0.5), 1, 1, color="black"))
                elif (r, c) in env.goals:
                    ax.text(c, r, "G", ha="center", va="center", fontsize=8, color="blue")
                elif (r, c) in env.traps:
                    ax.text(c, r, "T", ha="center", va="center", fontsize=8, color="red")

        plt.tight_layout()
        plt.savefig("value_function.png")
        print("Value function heatmap saved to value_function.png")
    except ImportError:
        pass


if __name__ == "__main__":
    main()
