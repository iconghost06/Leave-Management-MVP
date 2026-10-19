const LEAVE_TYPE_LABELS = { EARNED: "Earned", SICK: "Sick" };

export const LEAVE_TYPES = Object.keys(LEAVE_TYPE_LABELS);

export function leaveTypeLabel(leaveType) {
  return LEAVE_TYPE_LABELS[leaveType] || leaveType;
}
