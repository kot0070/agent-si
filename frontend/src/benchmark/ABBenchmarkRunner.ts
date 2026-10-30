// OC-K07 (ARCH-563): ABBenchmarkRunner keeps repeatable cloud-only
// versus local-assisted arms on identical task class. Both arms run the
// same task list in the same seeded order; the caller supplies the arm
// runner (a route client in product, a local function in tests), so this
// module never touches the network itself. Deltas are local-assisted
// minus cloud-only. Repeatability: the same seed plus the same tasks
// yields the same report.

export const AB_ARM_CLOUD_ONLY = "cloud-only";

export const AB_ARM_LOCAL_ASSISTED = "local-assisted";

export const AB_ARMS = [AB_ARM_CLOUD_ONLY, AB_ARM_LOCAL_ASSISTED] as const;

export type ABArm = (typeof AB_ARMS)[number];

export interface ABTask {
  taskId: string;
  taskClass: string;
}

export interface ABArmRun {
  arm: ABArm;
  taskId: string;
  completed: boolean;
  score: number;
}

export interface ABArmTotals {
  arm: ABArm;
  runs: number;
  completed: number;
  totalScore: number;
}

export interface ABReport {
  taskClass: string;
  seed: number;
  totals: ABArmTotals[];
  completedDelta: number;
  scoreDelta: number;
  runs: ABArmRun[];
}

export interface ABSingleResult {
  completed: boolean;
  score: number;
}

export type ABRunOne = (
  arm: ABArm,
  task: ABTask,
) => Promise<ABSingleResult>;

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let mixed = state;
    mixed = Math.imul(mixed ^ (mixed >>> 15), mixed | 1);
    mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61);
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
}

function seededOrder(tasks: ABTask[], seed: number): ABTask[] {
  const order = [...tasks];
  const random = mulberry32(seed);
  for (let i = order.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    const swap = order[i];
    order[i] = order[j];
    order[j] = swap;
  }
  return order;
}

export class ABBenchmarkRunner {
  private readonly seed: number;
  private readonly runOne: ABRunOne;

  constructor(seed: number, runOne: ABRunOne) {
    if (!Number.isInteger(seed)) {
      throw new Error(
        `AB_INVALID_SEED: seed must be an integer, got ${String(seed)}`,
      );
    }
    this.seed = seed;
    this.runOne = runOne;
  }

  async run(taskClass: string, tasks: ABTask[]): Promise<ABReport> {
    if (taskClass.trim().length === 0) {
      throw new Error("AB_EMPTY_TASK_CLASS: task class must not be blank");
    }
    if (tasks.length === 0) {
      throw new Error("AB_EMPTY_TASK_LIST: at least one task is required");
    }
    for (const task of tasks) {
      if (task.taskClass !== taskClass) {
        throw new Error(
          `AB_TASK_CLASS_MISMATCH: task ${task.taskId} carries ` +
            `${task.taskClass}, expected ${taskClass}`,
        );
      }
    }
    const order = seededOrder(tasks, this.seed);
    const runs: ABArmRun[] = [];
    for (const arm of AB_ARMS) {
      for (const task of order) {
        const single = await this.runOne(arm, task);
        runs.push({
          arm,
          taskId: task.taskId,
          completed: single.completed,
          score: single.score,
        });
      }
    }
    const totals: ABArmTotals[] = AB_ARMS.map((arm) => {
      const armRuns = runs.filter((entry) => entry.arm === arm);
      return {
        arm,
        runs: armRuns.length,
        completed: armRuns.filter((entry) => entry.completed).length,
        totalScore: armRuns.reduce((sum, entry) => sum + entry.score, 0),
      };
    });
    const cloud = totals[0];
    const local = totals[1];
    return {
      taskClass,
      seed: this.seed,
      totals,
      completedDelta: local.completed - cloud.completed,
      scoreDelta: local.totalScore - cloud.totalScore,
      runs,
    };
  }
}
