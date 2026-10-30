# Fieldwork portal friction and public-archive research — October 30, 2026

Research notes for future development. This file contains public policy and workflow information only, **not** user request data. No portal logins were performed, and no live autofill compatibility is certified.

## Operational findings

1. **NextRequest initial filing may be guest-first.** Vendor documentation says an email entered when submitting a first request creates the requester account; a password is not always required before filing. Agency-specific exceptions exist. https://www.civicplus.help/nextrequest/docs/submit-a-request-and-create-a-public-account
2. **GovQA login rules differ by deployment.** Multnomah County Sheriff explicitly requires an account. Phoenix's public GovQA tutorial requires account setup on the first request. Do not label every GovQA instance as mandatory-account without testing its agency-specific portal. https://www.mcso.us/how-do-i/public-records-requests ; https://uploads.govqa.us/CITYOFPHOENIXAZ/Public_Portal_How-To_Guide.pdf
3. **Some agencies allow request-form or email filing, but delivery later requires an account.** Douglas County Sheriff (NV) accepts emailed signed BWC forms (one case per form; $1 per released video), but Evidence.com links require an account and expire seven days from transmission. https://sheriff.douglascountynv.gov/UserFiles/Servers/Server_16087630/File/Body-Worn%20Camera%20Request.pdf
4. **A public archive should be checked before filing.** NextRequest supports public indexes and published requests/documents accessible without requiring an account where agency staff have published them. Publishing is agency-controlled; never assume every response or video is listed. https://www.civicplus.help/nextrequest/docs/add-manage-documents ; https://www.civicplus.help/nextrequest/docs/request-visibility
5. **Agency portal categories are not interchangeable.** Miami-Dade Sheriff displays separate General Public Records and Media Request routes. The selection must reflect actual requester status. https://miamidadecountyfl.govqa.us/WEBAPP/_rs/SupportHome.aspx
6. **Ordinary FOIA requests do not universally give access to BWC.** El Segundo Police's public FAQ says routine BWC/dashcam requests generally require subpoena unless state law requires release. Block ordinary bulk BWC requests to this agency; leave exceptions for manual review. https://cityofelsegundocapd.nextrequest.com/faqs
7. **Publicly viewable request histories can provide tentative outcome evidence, not universal success rates.** Providence RI NextRequest has examples of individual BWC requests withheld on privacy grounds. Do not convert a few examples into general agency success scores, and do not redistribute personal case details. https://providenceri.nextrequest.com/requests/26-2073 ; https://providenceri.nextrequest.com/requests/26-2104

## Product backlog, highest value

- Add **submission stage** and **delivery stage** separately to each portal profile (no account / optional account / account needed / unknown).
- Add **preflight public archive search** to story cards. Flag "public documents found", "request already publicly covered", or "archive not supported". Finding a public release is not proof commercial reuse is authorized.
- Add signed-form/email mode for agencies that permit it, keeping all signatures and legal attestations in user's control.
- Track delivery-link expiry and prompt users to save authorized footage before it expires; never collect passwords, cookies, or authentication tokens.
- Distinguish forms live-tested in browser from source-described processes, and never promise autofill based solely on platform branding.
- Maintain an evidence denominator when measuring success; don't label an agency reliable from one disclosed or denied public request.

## Security and scope

These notes are research instructions, not a substitute for laws or agency form review. Incidents may be withheld for privacy, active investigations or specialized statutes, regardless of portal convenience. Publishing recorded footage commercially can require additional review.
