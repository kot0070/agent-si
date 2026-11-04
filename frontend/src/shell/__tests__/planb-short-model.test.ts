// PLANB V2e: the one-line team row keeps the tag of a local model.
import { describe, expect, it } from "vitest";
import { shortModelName } from "../Inspector";

describe("shortModelName", () => {
  it("keeps the Ollama tag of a local model", () => {
    expect(shortModelName("ollama/muse-glimmer:30b")).toBe("muse-glimmer:30b");
    expect(shortModelName("muse-glimmer:30b")).toBe("muse-glimmer:30b");
  });
  it("still drops the provider prefix of a cloud id", () => {
    expect(shortModelName("meta/muse-spark-1.3-contributor")).toBe(
      "muse-spark-1.3-contributor",
    );
    expect(shortModelName("meta-llama/long-model-name-70b")).toBe(
      "long-model-name-70b",
    );
  });
});
