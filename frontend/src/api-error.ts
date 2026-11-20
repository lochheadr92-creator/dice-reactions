/**
 * Typed HTTP error for API responses. Preserves status and parsed backend detail.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly detail?: string;
  readonly body?: unknown;
  readonly rawText: string;

  constructor(status: number, rawText: string, detail?: string, body?: unknown) {
    const message = detail || rawText.trim() || `HTTP ${status}`;
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.rawText = rawText;
    this.detail = detail;
    this.body = body;
  }

  static async fromResponse(res: Response): Promise<ApiError> {
    const text = await res.text();
    let detail: string | undefined;
    let body: unknown;
    try {
      body = JSON.parse(text);
      if (body && typeof body === "object" && "detail" in body) {
        const parsed = (body as { detail: unknown }).detail;
        if (typeof parsed === "string") {
          detail = parsed;
        }
      }
    } catch {
      // Non-JSON bodies fall back to raw text.
    }
    if (!detail && text.trim()) {
      detail = text.trim().slice(0, 500);
    }
    return new ApiError(res.status, text, detail, body);
  }

  static isConflict(error: unknown): error is ApiError {
    return error instanceof ApiError && error.status === 409;
  }

  /** 409 raised because the same action_request_id was reused with different contents. */
  static isRequestMismatch(error: unknown): boolean {
    return (
      error instanceof ApiError &&
      error.status === 409 &&
      typeof error.detail === "string" &&
      /action_request_id/i.test(error.detail)
    );
  }

  static isNotFound(error: unknown): boolean {
    return error instanceof ApiError && error.status === 404;
  }

  static isRateLimited(error: unknown): boolean {
    return error instanceof ApiError && error.status === 429;
  }

  static isValidation(error: unknown): boolean {
    return error instanceof ApiError && (error.status === 422 || error.status === 400);
  }

  /** Server failure where the outcome is not known to have happened (retry with the same id). */
  static isRetryableServerError(error: unknown): boolean {
    return error instanceof ApiError && (error.status === 502 || error.status === 503);
  }
}