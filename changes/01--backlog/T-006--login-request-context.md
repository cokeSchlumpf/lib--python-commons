# T-006 Request context for the login mail

## Problem

The login mail of `SMTPLoginTokenSender` (T-005) can only be chosen from the `LoginTokenMessage` and its user. What is known only at the request, such as the browser's language or the app's current locale, can't reach the mail, because `LoginTokenService.request_login` and `SendLoginTokenPort` don't carry it and pyhx `EmailTokenLogin` doesn't pass it.

## Proposed outcome

- An app can pass request context (at least the language) from pyhx into the login request, and the sender can use it to choose subject, text and HTML of the mail.
