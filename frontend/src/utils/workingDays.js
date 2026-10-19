const MS_PER_DAY = 24 * 60 * 60 * 1000;

// "YYYY-MM-DD" -> whole days since 1970-01-01 (UTC, so the browser's time zone cannot shift it).
function toDayNumber(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return Math.round(Date.UTC(year, month - 1, day) / MS_PER_DAY);
}

// Mon-Fri dates in [start, end] inclusive, holidays ignored (R4). This is a preview only: the
// server counts again and is the authority. Returns 0 for missing or reversed dates.
export function countWorkingDays(start, end) {
  if (!start || !end) return 0;
  const first = toDayNumber(start);
  const last = toDayNumber(end);
  if (Number.isNaN(first) || Number.isNaN(last) || last < first) return 0;

  const total = last - first + 1;
  let count = Math.floor(total / 7) * 5;
  // The leftover 0-6 days: 1970-01-01 was a Thursday, so (day + 4) % 7 is 0 for Sunday.
  for (let day = first + Math.floor(total / 7) * 7; day <= last; day += 1) {
    const weekday = (day + 4) % 7;
    if (weekday !== 0 && weekday !== 6) count += 1;
  }
  return count;
}
