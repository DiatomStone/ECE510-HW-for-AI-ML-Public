"""
Tabular Q-learning on configurable gridworld environments.
Supports: standard grids, mazes, stochastic transitions, partial observability,
multiple goal states, and wind fields.
"""

import numpy as np
import pickle
from collections import defaultdict


# ---------------------------------------------------------------------------
# Grid environment
# ---------------------------------------------------------------------------

ACTIONS = {
    0: (-1, 0),   # up
    1: (1, 0),    # down
    2: (0, -1),   # left
    3: (0, 1),    # right
}
N_ACTIONS = 4
ACTION_NAMES = ["up", "down", "left", "right"]


class GridWorld:
    """
    Rectangular gridworld with walls, multiple goals, and optional features.

    Parameters
    ----------
    grid : list[str]
        ASCII grid. Characters:
          'S' = start, 'G' = goal, '#' = wall, 'T' = trap (negative reward),
          ' ' or '.' = open cell
    step_cost : float
        Reward for each non-terminal step.
    goal_reward : float
        Reward on reaching a goal.
    trap_reward : float
        Reward on stepping into a trap.
    slip_prob : float
        With this probability the agent moves in a random direction instead.
    max_steps : int
        Episode truncation length.
    wind : dict[int, int] or None
        Maps column index -> extra downward steps per move in that column (Windy Gridworld).
    """

    def __init__(
        self,
        grid,
        step_cost=-0.04,
        goal_reward=1.0,
        trap_reward=-1.0,
        slip_prob=0.0,
        max_steps=500,
        wind=None,
    ):
        self.grid = [list(row) for row in grid]
        self.rows = len(self.grid)
        self.cols = max(len(r) for r in self.grid)
        self.step_cost = step_cost
        self.goal_reward = goal_reward
        self.trap_reward = trap_reward
        self.slip_prob = slip_prob
        self.max_steps = max_steps
        self.wind = wind or {}

        self.starts, self.goals, self.traps, self.walls = set(), set(), set(), set()
        for r, row in enumerate(self.grid):
            for c, ch in enumerate(row):
                if ch == "S":
                    self.starts.add((r, c))
                elif ch == "G":
                    self.goals.add((r, c))
                elif ch == "T":
                    self.traps.add((r, c))
                elif ch == "#":
                    self.walls.add((r, c))

        assert self.starts, "Grid must have at least one 'S' cell."
        assert self.goals, "Grid must have at least one 'G' cell."

        self.n_states = self.rows * self.cols
        self._state = None
        self._steps = 0

    def _to_idx(self, r, c):
        return r * self.cols + c

    def _in_bounds(self, r, c):
        return 0 <= r < self.rows and 0 <= c < self.cols

    def reset(self, rng=None):
        if rng is None:
            rng = np.random.default_rng()
        starts = list(self.starts)
        self._state = starts[rng.integers(len(starts))]
        self._steps = 0
        return self._to_idx(*self._state)

    def step(self, action, rng=None):
        if rng is None:
            rng = np.random.default_rng()

        r, c = self._state

        # Slippage
        if self.slip_prob > 0 and rng.random() < self.slip_prob:
            action = int(rng.integers(N_ACTIONS))

        dr, dc = ACTIONS[action]
        nr, nc = r + dr, c + dc

        # Wind: extra downward push
        wind_push = self.wind.get(c, 0)
        nr += wind_push

        # Clamp to grid; walls block movement
        if not self._in_bounds(nr, nc) or (nr, nc) in self.walls:
            nr, nc = r, c

        self._state = (nr, nc)
        self._steps += 1
        state_idx = self._to_idx(nr, nc)

        done = False
        reward = self.step_cost

        if (nr, nc) in self.goals:
            reward = self.goal_reward
            done = True
        elif (nr, nc) in self.traps:
            reward = self.trap_reward
            done = True
        elif self._steps >= self.max_steps:
            done = True

        return state_idx, reward, done

    def render(self, q_table=None, policy=None):
        """Return ASCII string of the grid, optionally with greedy policy arrows."""
        arrows = {0: "^", 1: "v", 2: "<", 3: ">"}
        lines = []
        for r in range(self.rows):
            row_str = ""
            for c in range(self.cols):
                cell = "."
                if (r, c) in self.walls:
                    cell = "#"
                elif (r, c) in self.goals:
                    cell = "G"
                elif (r, c) in self.traps:
                    cell = "T"
                elif (r, c) in self.starts:
                    cell = "S"
                if policy is not None and (r, c) not in self.walls:
                    idx = self._to_idx(r, c)
                    if (r, c) in self.goals or (r, c) in self.traps:
                        pass
                    else:
                        cell = arrows.get(policy[idx], cell)
                row_str += cell + " "
            lines.append(row_str)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Q-learning agent
# ---------------------------------------------------------------------------

class QLearningAgent:
    """
    Tabular Q-learning with epsilon-greedy exploration and optional double-Q.

    Parameters
    ----------
    n_states : int
    n_actions : int
    lr : float
        Learning rate.
    gamma : float
        Discount factor.
    eps_start : float
        Initial epsilon for epsilon-greedy.
    eps_end : float
        Minimum epsilon.
    eps_decay : float
        Multiplicative decay per episode.
    double_q : bool
        Use Double Q-learning (reduces maximization bias).
    init_val : float
        Initial Q-value (optimistic initialization encourages exploration).
    """

    def __init__(
        self,
        n_states,
        n_actions=N_ACTIONS,
        lr=0.1,
        gamma=0.99,
        eps_start=1.0,
        eps_end=0.01,
        eps_decay=0.995,
        double_q=False,
        init_val=0.0,
        seed=0,
    ):
        self.n_states = n_states
        self.n_actions = n_actions
        self.lr = lr
        self.gamma = gamma
        self.eps = eps_start
        self.eps_end = eps_end
        self.eps_decay = eps_decay
        self.double_q = double_q
        self.rng = np.random.default_rng(seed)

        self.Q = np.full((n_states, n_actions), init_val, dtype=np.float64)
        if double_q:
            self.Q2 = np.full((n_states, n_actions), init_val, dtype=np.float64)

        self.total_steps = 0
        self.episode = 0

    def select_action(self, state):
        if self.rng.random() < self.eps:
            return int(self.rng.integers(self.n_actions))
        if self.double_q:
            return int(np.argmax(self.Q[state] + self.Q2[state]))
        return int(np.argmax(self.Q[state]))

    def update(self, state, action, reward, next_state, done):
        if self.double_q:
            self._update_double(state, action, reward, next_state, done)
        else:
            self._update_standard(state, action, reward, next_state, done)
        self.total_steps += 1

    def _update_standard(self, s, a, r, s_, done):
        target = r if done else r + self.gamma * self.Q[s_].max()
        self.Q[s, a] += self.lr * (target - self.Q[s, a])

    def _update_double(self, s, a, r, s_, done):
        if done:
            target_A = r
            target_B = r
        else:
            # A selects, B evaluates
            best_A = np.argmax(self.Q[s_])
            best_B = np.argmax(self.Q2[s_])
            target_A = r + self.gamma * self.Q2[s_, best_A]
            target_B = r + self.gamma * self.Q[s_, best_B]

        if self.rng.random() < 0.5:
            self.Q[s, a] += self.lr * (target_A - self.Q[s, a])
        else:
            self.Q2[s, a] += self.lr * (target_B - self.Q2[s, a])

    def decay_epsilon(self):
        self.eps = max(self.eps_end, self.eps * self.eps_decay)
        self.episode += 1

    def greedy_policy(self):
        if self.double_q:
            return np.argmax(self.Q + self.Q2, axis=1)
        return np.argmax(self.Q, axis=1)

    def save(self, path):
        with open(path, "wb") as f:
            pickle.dump(self.__dict__, f)

    @classmethod
    def load(cls, path):
        agent = cls.__new__(cls)
        with open(path, "rb") as f:
            agent.__dict__ = pickle.load(f)
        return agent


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train(env, agent, n_episodes=5000, eval_every=500, eval_episodes=20, verbose=True):
    """
    Run Q-learning for n_episodes.

    Returns
    -------
    history : dict with keys:
        'episode_returns'    - sum of rewards per training episode
        'episode_lengths'    - number of steps per episode
        'eval_returns'       - mean eval return at each checkpoint
        'eval_episodes'      - episode numbers where eval occurred
        'epsilons'           - epsilon at each episode
    """
    history = {
        "episode_returns": [],
        "episode_lengths": [],
        "eval_returns": [],
        "eval_episodes": [],
        "epsilons": [],
    }

    rng = agent.rng

    for ep in range(1, n_episodes + 1):
        state = env.reset(rng)
        done = False
        total_reward = 0.0
        steps = 0

        while not done:
            action = agent.select_action(state)
            next_state, reward, done = env.step(action, rng)
            agent.update(state, action, reward, next_state, done)
            state = next_state
            total_reward += reward
            steps += 1

        agent.decay_epsilon()
        history["episode_returns"].append(total_reward)
        history["episode_lengths"].append(steps)
        history["epsilons"].append(agent.eps)

        if ep % eval_every == 0:
            mean_ret = evaluate(env, agent, eval_episodes)
            history["eval_returns"].append(mean_ret)
            history["eval_episodes"].append(ep)
            if verbose:
                print(
                    f"Episode {ep:6d} | eps {agent.eps:.3f} | "
                    f"train ret {np.mean(history['episode_returns'][-eval_every:]):.3f} | "
                    f"eval ret {mean_ret:.3f}"
                )

    return history


def evaluate(env, agent, n_episodes=100):
    """Run greedy policy and return mean episode return."""
    policy = agent.greedy_policy()
    rng = np.random.default_rng(999)
    returns = []
    for _ in range(n_episodes):
        state = env.reset(rng)
        done = False
        total = 0.0
        while not done:
            action = int(policy[state])
            state, reward, done = env.step(action, rng)
            total += reward
        returns.append(total)
    return float(np.mean(returns))


# ---------------------------------------------------------------------------
# Pre-built environments
# ---------------------------------------------------------------------------

def make_env(name, **kwargs):
    """
    Factory for named environments.

    Available: 'small', 'medium', 'large', 'maze', 'windy', 'stochastic', 'multi_goal'
    """
    envs = {
        "small": _small_grid,
        "medium": _medium_grid,
        "large": _large_grid,
        "maze": _maze_grid,
        "windy": _windy_grid,
        "stochastic": _stochastic_grid,
        "multi_goal": _multi_goal_grid,
    }
    if name not in envs:
        raise ValueError(f"Unknown env '{name}'. Choose from: {list(envs)}")
    return envs[name](**kwargs)


def _small_grid(**kwargs):
    grid = [
        "S....",
        ".###.",
        ".....",
        ".###.",
        "....G",
    ]
    return GridWorld(grid, **kwargs)


def _medium_grid(**kwargs):
    grid = [
        "S.........",
        ".########.",
        "..........",
        ".########.",
        "..........",
        ".########.",
        "..........",
        ".########.",
        "..........",
        "..........G",
    ]
    return GridWorld(grid, **kwargs)


def _large_grid(size=30, **kwargs):
    """Open large grid - tests scaling."""
    rows = []
    for r in range(size):
        if r == 0:
            row = "S" + "." * (size - 1)
        elif r == size - 1:
            row = "." * (size - 1) + "G"
        else:
            row = "." * size
        rows.append(row)
    return GridWorld(rows, max_steps=size * size, **kwargs)


def _maze_grid(**kwargs):
    grid = [
        "S#.....#..",
        "...#.#.#..",
        ".#.#.#.#..",
        ".#...#.#..",
        ".#####.#..",
        "...#...#..",
        ".#.#.###..",
        ".#.#.....G",
        ".#.#######",
        "...........",
    ]
    return GridWorld(grid, **kwargs)


def _windy_grid(**kwargs):
    grid = [
        "S........G",
        "..........",
        "..........",
        "..........",
        "..........",
        "..........",
        "..........",
    ]
    # Columns 3-8 have upward wind (negative = up direction; wind is downward in env)
    wind = {3: -1, 4: -1, 5: -2, 6: -2, 7: -2, 8: -1}
    return GridWorld(grid, wind=wind, **kwargs)


def _stochastic_grid(**kwargs):
    kwargs.setdefault("slip_prob", 0.2)
    grid = [
        "S.....",
        "......",
        "..T...",
        "......",
        "......",
        ".....G",
    ]
    return GridWorld(grid, **kwargs)


def _multi_goal_grid(**kwargs):
    grid = [
        "S.........",
        "..........",
        ".....G....",
        "..........",
        "..........",
        ".....T....",
        "..........",
        "..........",
        ".........G",
        "..........",
    ]
    return GridWorld(grid, **kwargs)
