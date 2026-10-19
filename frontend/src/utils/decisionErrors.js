// Decision errors that mean "this request is no longer actionable as shown": the dialog closes, the
// message goes in the page banner and the page refetches. Any other error (for example
// COMMENT_REQUIRED) stays in the dialog so the manager can correct it.
export const CLOSING_ERRORS = {
  ALREADY_ACTIONED: "This request has already been decided.",
  INSUFFICIENT_BALANCE: "The employee does not have enough balance to approve this request.",
  SELF_ACTION_FORBIDDEN: "You cannot act on your own request.",
  NOT_REQUESTERS_MANAGER: "Only this person's manager can decide this request",
};
