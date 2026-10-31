import { describe, expect, it } from "vitest";
import {
  ABBenchmarkRunner,
  AB_ARMS,
  type ABRunOne,
  type ABTask,
} from "../ABBenchmarkRunner";

const TASKS: ABTask[] = [
  { taskId: "t-1", taskClass: "bench-class" },
  { taskId: "t-2", taskClass: "bench-class" },
  { taskId: "t-3", taskClass: "bench-class" },
  { taskId: "t-4", taskClass: "bench-class" },
  { taskId: "t-5", taskClass: "bench-class" },
  { taskId: "t-6", taskClass: "bench-class" },
  { taskId: "t-7", taskClass: "bench-class" },
  { taskId: "t-8", taskClass: "bench-class" },
];

const DETERMINISTIC: ABRunOne = async (arm, task) => ({
  completed: task.taskId !== "t-8" || arm === "local-assisted",
  score: task.taskId.length + (arm === "local-assisted" ? 1 : 0),
});

describe("ABBenchmarkRunner", () => {
  it("runs both arms over the identical task list in the same order", async () => {
    const runner = new ABBenchmarkRunner(7, DETERMINISTIC);
    const report = await runner.run("bench-class", TASKS);
    expect(report.taskClass).toBe("bench-class");
    expect(report.seed).toBe(7);
    const orders = AB_ARMS.map((arm) =>
      report.runs.filter((entry) => entry.arm === arm).map((entry) => entry.taskId),
    );
    expect(orders[0]).toEqual(orders[1]);
    expect(orders[0]).toHaveLength(TASKS.length);
    expect(report.totals.map((total) => total.arm)).toEqual([...AB_ARMS]);
  });

  it("is repeatable for the same seed and tasks", async () => {
    const first = await new ABBenchmarkRunner(7, DETERMINISTIC).run(
      "bench-class",
      TASKS,
    );
    const second = await new ABBenchmarkRunner(7, DETERMINISTIC).run(
      "bench-class",
      TASKS,
    );
    expect(second).toEqual(first);
  });

  it("orders differently for different seeds", async () => {
    const first = await new ABBenchmarkRunner(7, DETERMINISTIC).run(
      "bench-class",
      TASKS,
    );
    const second = await new ABBenchmarkRunner(8, DETERMINISTIC).run(
      "bench-class",
      TASKS,
    );
    const orderOf = (seed: number): string[] =>
      (seed === 7 ? first : second).runs
        .filter((entry) => entry.arm === "cloud-only")
        .map((entry) => entry.taskId);
    expect(orderOf(8)).not.toEqual(orderOf(7));
  });

  it("reports local-assisted minus cloud-only deltas", async () => {
    const report = await new ABBenchmarkRunner(7, DETERMINISTIC).run(
      "bench-class",
      TASKS,
    );
    const cloud = report.totals[0];
    const local = report.totals[1];
    expect(cloud.completed).toBe(7);
    expect(local.completed).toBe(8);
    expect(report.completedDelta).toBe(
      local.completed - cloud.completed,
    );
    expect(report.scoreDelta).toBe(local.totalScore - cloud.totalScore);
    expect(report.scoreDelta).toBe(TASKS.length);
  });

  it("rejects a blank task class", async () => {
    const runner = new ABBenchmarkRunner(7, DETERMINISTIC);
    await expect(runner.run("  ", TASKS)).rejects.toThrow(
      /AB_EMPTY_TASK_CLASS/,
    );
  });

  it("rejects an empty task list", async () => {
    const runner = new ABBenchmarkRunner(7, DETERMINISTIC);
    await expect(runner.run("bench-class", [])).rejects.toThrow(
      /AB_EMPTY_TASK_LIST/,
    );
  });

  it("rejects a task from another class", async () => {
    const runner = new ABBenchmarkRunner(7, DETERMINISTIC);
    await expect(
      runner.run("bench-class", [
        ...TASKS,
        { taskId: "t-x", taskClass: "other-class" },
      ]),
    ).rejects.toThrow(/AB_TASK_CLASS_MISMATCH/);
  });

  it("rejects a non-integer seed", () => {
    expect(() => new ABBenchmarkRunner(1.5, DETERMINISTIC)).toThrow(
      /AB_INVALID_SEED/,
    );
  });
});
