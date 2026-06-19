import { ApiError } from "../src/api-error";
import {
  friendlyError,
  ACTION_CONFLICT_MESSAGE,
  ACTION_CONFLICT_TITLE,
} from "../src/errors";

describe("ApiError", () => {
  it("retains status 409 and parsed JSON detail", async () => {
    const res = new Response(
      JSON.stringify({ detail: "An action is already in progress for this chronicle" }),
      { status: 409, headers: { "Content-Type": "application/json" } }
    );
    const err = await ApiError.fromResponse(res);
    expect(err.status).toBe(409);
    expect(err.detail).toBe("An action is already in progress for this chronicle");
    expect(ApiError.isConflict(err)).toBe(true);
  });

  it("falls back to plain-text error body", async () => {
    const res = new Response("service unavailable", { status: 503 });
    const err = await ApiError.fromResponse(res);
    expect(err.status).toBe(503);
    expect(err.detail).toBe("service unavailable");
  });

  it("does not throw when error body is invalid JSON", async () => {
    const res = new Response("{not-json", { status: 500 });
    await expect(ApiError.fromResponse(res)).resolves.toBeInstanceOf(ApiError);
  });
});

describe("friendlyError", () => {
  it("maps 409 ApiError to player-safe copy without promising future sync", async () => {
    const err = await ApiError.fromResponse(
      new Response(JSON.stringify({ detail: "An action is already in progress for this chronicle" }), {
        status: 409,
      })
    );
    const out = friendlyError(err);
    expect(out.title).toBe(ACTION_CONFLICT_TITLE);
    expect(out.message).toBe(ACTION_CONFLICT_MESSAGE);
    expect(out.message.toLowerCase()).not.toContain("automatically");
    expect(out.message.toLowerCase()).not.toContain("will be synced");
    expect(out.message.toLowerCase()).not.toContain("lease");
    expect(out.message.toLowerCase()).not.toContain("token");
    expect(out.message.toLowerCase()).not.toContain("lock");
    expect(out.message.toLowerCase()).not.toContain("concurrency");
  });

  it("keeps existing 402 mapping", () => {
    const out = friendlyError(new Error('502: {"detail":"OpenRouter HTTP 402: Insufficient credits"}'));
    expect(out.title).toBe("Out of credits");
  });

  it("keeps existing 429 mapping", () => {
    const out = friendlyError(new Error("OpenRouter HTTP 429: rate-limited"));
    expect(out.title).toBe("Model is busy");
  });

  it("keeps existing 5xx mapping", () => {
    const out = friendlyError(new Error("502: Story engine error"));
    expect(out.title).toBe("Engine hesitated");
  });
});