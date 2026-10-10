/**
 * 统一错误类型。后端失败响应（docs/08 §0.2、§0.5）：
 * { code: 1, data: { error_code: "<machine_code>" }, msg: "<human message>" }
 */

export type ApiErrorCode =
  | 'unauthorized'
  | 'permission_denied'
  | 'not_found'
  | 'conflict'
  | 'validation_error'
  | 'external_service_error'
  | 'app_error'
  | (string & {}); // 契约外的新错误码不崩前端，交给 UI 兜底

export class ApiError extends Error {
  readonly errorCode: ApiErrorCode;
  readonly httpStatus: number;
  /** validation_error 时为 pydantic errors 数组，供表单内联纠错 */
  readonly data: unknown;

  constructor(errorCode: ApiErrorCode, message: string, httpStatus: number, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.errorCode = errorCode;
    this.httpStatus = httpStatus;
    this.data = data;
  }

  get isUnauthorized(): boolean {
    return this.errorCode === 'unauthorized' || this.httpStatus === 401;
  }
}

/** 网络层失败（超时、断网、非 JSON 响应等），与业务错误区分 */
export class NetworkError extends Error {
  constructor(cause?: unknown) {
    super('网络请求失败，请稍后重试');
    this.name = 'NetworkError';
    this.cause = cause;
  }
}

/** 微信登录返回 NeedInviteCodeError 时抛出，UI 引导走邀请码加入流程 */
export class NeedInviteCodeError extends ApiError {
  constructor(httpStatus: number) {
    super('need_invite_code', '账号不存在，需要邀请码加入家庭', httpStatus);
    this.name = 'NeedInviteCodeError';
  }
}
