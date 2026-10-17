/*
  What an API failure says to the person who caused it.

  FastAPI answers a handled failure with `detail` as a string, and a request
  rejected before it reached that handling (a 422 from pydantic) with
  `detail` as an array of error objects. The array is not a message, and
  rendering it as one put an unreadable object - or nothing - in front of
  the person who needs to read it.

  So: only a non-empty string is shown, trimmed; anything else - an array,
  an empty sentence, a request that never got an answer - falls back to the
  page's own message, which at least says what the page was trying to do.

  This lives apart from `api.ts` so it can be tested directly: importing the
  api client would drag axios and the whole request pipeline into the test.
*/

export function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (
    error as {
      response?: { data?: { detail?: unknown } };
    }
  )?.response?.data?.detail;

  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim();
  }

  return fallback;
}
