/**
 * BioInfoJobs Job Match — anonymous search logger.
 *
 * Receives one POST per completed quiz on match.html and appends a row to a
 * Google Sheet. Logs NO personal data — no IP, no user agent, no cookies,
 * no identifier of any kind. Just: when, and what was searched for.
 *
 * SETUP (one-time, ~5 minutes, completely free):
 * 1. Go to https://sheets.google.com and create a new blank spreadsheet.
 *    Name it e.g. "BioInfoJobs — Match Searches".
 * 2. In the sheet, go to Extensions → Apps Script.
 * 3. Delete the placeholder code and paste this entire file in its place.
 * 4. Click Deploy → New deployment.
 *    - Click the gear icon next to "Select type" → choose "Web app".
 *    - Description: anything, e.g. "search logger".
 *    - Execute as: Me.
 *    - Who has access: Anyone.
 * 5. Click Deploy. Google will ask you to authorize — click "Authorize
 *    access", pick your account, then (since it's your own unpublished
 *    script) click "Advanced" → "Go to <project name> (unsafe)" → Allow.
 *    This warning is normal for personal scripts; you're only authorizing
 *    yourself.
 * 6. Copy the "Web app URL" shown after deployment (ends in /exec).
 * 7. Paste that URL into the SEARCH_LOG_ENDPOINT constant near the top of
 *    match.html's <script> section.
 *
 * That's it — every completed search on match.html will append a row here.
 * Open the sheet any time to see raw entries, or build a pivot table on
 * column A (date) to see search volume/trends over time, and on columns
 * D/E (Tech / Interest) to see the most-requested skills and topics.
 *
 * If you ever want to stop logging, just clear SEARCH_LOG_ENDPOINT back to
 * "" in match.html — no changes needed here.
 */

function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Searches');
  if (!sheet) {
    sheet = SpreadsheetApp.getActiveSpreadsheet().insertSheet('Searches');
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      'Logged at (server)', 'Logged at (client)', 'Seniority',
      'Tech', 'Interest', 'Region', 'Active matches', 'Archived matches',
    ]);
  }

  var data = {};
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    data = {};
  }

  sheet.appendRow([
    new Date(),
    data.timestamp || '',
    data.seniority || '',
    (data.tech || []).join(', '),
    (data.interest || []).join(', '),
    data.geo || '',
    data.activeCount != null ? data.activeCount : '',
    data.archivedCount != null ? data.archivedCount : '',
  ]);

  return ContentService
    .createTextOutput(JSON.stringify({ status: 'ok' }))
    .setMimeType(ContentService.MimeType.JSON);
}
