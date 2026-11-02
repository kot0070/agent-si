// @vitest-environment node
// FXCHATHIST Part 1: app-level per-project chat store (no DOM mount).
// The store lives above routes: messages plus the live runner state
// survive component unmount; the H4 verdict line (health) and the
// quiet dot state (online + offline queue) are part of the shape.
import { beforeEach, describe, expect, it } from "vitest";
import {
  appendChatMessage,
  clearChatQueue,
  dequeueChatPrompt,
  enqueueChatPrompt,
  getChatState,
  patchChatMessage,
  resetChatStore,
  setChatHealth,
  setChatOnline,
  setChatRunner,
} from "../chatStore";

beforeEach(() => {
  resetChatStore();
});

describe("chatStore per-project state", () => {
  it("starts empty per project", () => {
    const state = getChatState("p-1");
    expect(state.messages).toEqual([]);
    expect(state.runner).toEqual({ streamId: null, streaming: false });
    expect(state.health).toBe("ok");
    expect(state.online).toBe(true);
    expect(state.queue).toEqual([]);
  });

  it("isolates projects from each other", () => {
    appendChatMessage("p-1", { role: "user", text: "hello", final: true });
    expect(getChatState("p-1").messages).toHaveLength(1);
    expect(getChatState("p-2").messages).toEqual([]);
  });

  it("keeps messages plus the live runner state across unmount", () => {
    const first = appendChatMessage("p-1", {
      role: "user",
      text: "hello",
      final: true,
    });
    const assistant = appendChatMessage("p-1", {
      role: "assistant",
      text: "",
      final: false,
    });
    setChatRunner("p-1", { streamId: "s-1", streaming: true });
    // Unmount: drop every local reference; the module store survives.
    void first;
    const revived = getChatState("p-1");
    expect(revived.messages).toHaveLength(2);
    expect(revived.runner).toEqual({ streamId: "s-1", streaming: true });
    patchChatMessage("p-1", assistant.id, { text: "Hi", final: true });
    setChatRunner("p-1", { streamId: null, streaming: false });
    const done = getChatState("p-1");
    expect(done.messages[1]?.text).toBe("Hi");
    expect(done.messages[1]?.final).toBe(true);
    expect(done.runner.streaming).toBe(false);
  });

  it("carries the H4 verdict line in the shape", () => {
    setChatHealth("p-1", "degraded");
    expect(getChatState("p-1").health).toBe("degraded");
    setChatHealth("p-1", "reconnecting");
    expect(getChatState("p-1").health).toBe("reconnecting");
    setChatHealth("p-1", "ok");
    expect(getChatState("p-1").health).toBe("ok");
    // Other projects are unaffected.
    expect(getChatState("p-2").health).toBe("ok");
  });

  it("carries the quiet dot state: offline flag plus queued prompts", () => {
    setChatOnline("p-1", false);
    enqueueChatPrompt("p-1", "queued hello");
    enqueueChatPrompt("p-1", "queued again");
    const offline = getChatState("p-1");
    expect(offline.online).toBe(false);
    expect(offline.queue).toEqual(["queued hello", "queued again"]);
    setChatOnline("p-1", true);
    expect(dequeueChatPrompt("p-1")).toBe("queued hello");
    expect(dequeueChatPrompt("p-1")).toBe("queued again");
    expect(dequeueChatPrompt("p-1")).toBeUndefined();
    clearChatQueue("p-1");
    expect(getChatState("p-1").queue).toEqual([]);
  });

  it("records accept/reject decisions on assistant messages", () => {
    const assistant = appendChatMessage("p-1", {
      role: "assistant",
      text: "proposal",
      final: true,
    });
    patchChatMessage("p-1", assistant.id, { decided: "accepted" });
    expect(getChatState("p-1").messages[0]?.decided).toBe("accepted");
  });
});
