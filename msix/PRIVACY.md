# WAT Pro Privacy Policy

_Draft — adapt this to your actual practices before publication. Microsoft
Store requires a valid privacy policy (and a link to it) for any application
that accesses the network or stores credentials — our application does both
(SMTP, arbitrary web pages)._

## What the Application Does

WAT Pro is a local tool for testing and automating web pages. All scripts,
collected data, and settings are stored **locally on your computer** (`.json`
files, an SQLite database next to the application, or in
`%LOCALAPPDATA%\WAT Pro`).

## What Data Is Processed

- **SMTP password** (if you configure e-mail notifications) is stored using
  the Windows system storage (Credential Manager), not in plain text and is
  not transmitted to the application developer.
- **Script contents and collected data** remain local; they are not sent
  outside your computer, except when you configure an e-mail notification
  yourself — in that case, the e-mail is sent directly through the SMTP
  server you specify, without going through the developer.
- **Visited pages**: the application is a browser wrapper; it navigates to
  the URLs you specify yourself (in a script or in the address bar), just
  like a regular browser.

## What the Application Does NOT Do

- It does not collect or transmit data to the developer or third parties.
- It does not use analytics or telemetry.
- It does not automatically publish your scripts or collected data anywhere.

## Contact

Alexander Shibisty
shibisty.a@gmail.com
https://shibisty.com
