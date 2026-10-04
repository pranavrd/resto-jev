# 0001: Yelp dataset license and showcase scope

- **Status:** Accepted with amendments (2026-10-02), see "Owner update" below
- **Date:** 2026-10-02
- **Source read:** Yelp Dataset Terms of Use, last updated July 7, 2023 (`Dataset_User_Agreement.pdf`, linked from yelp.com/dataset)
- **Not legal advice.** This is a plain-language reading by the project owner and an AI assistant. Re-read the agreement shown at download time, since Yelp can change it (§2).

## Context

The roadmap assumed the Yelp Open Dataset is "for academic/personal use" and left the hosted-demo question open (Phase 9). The agreement is stricter than that summary.

## Owner update (2026-10-02)

- The project is **not tied to UW or any course or institution.** Taken at face value, that means it does not clearly meet the "academic use" definition in §1/§3, so Yelp data use needs Yelp's written consent or a different framing before anything public.
- **No consent email for now.** Yelp use is deferred until the project reaches the Yelp join (see 0002). The assistant reminds the owner before the first Yelp download or query, and the email draft below is the starting point at that time.
- Until then the project runs on non-Yelp sources only (OSM, Mapillary, OpenDataPhilly), which have no showcase restrictions beyond attribution.
- The decisions below still hold, with the consent email moved from "this week" to "before touching Yelp data". The open item about UW affiliation is closed (no affiliation).

## Owner note on public hosting (2026-10-03)

The owner read the Yelp Open Dataset terms and summarised them as: a personal project may be hosted publicly if it is (1) free, with no ads, subscription, lead generation or paywall, (2) does not redistribute the raw JSON or CSV, so users get the data from Yelp, and (3) carries a prominent notice that the data belongs to Yelp and came from the Yelp Open Dataset. The summary also says code, results and visualisations can be shown.

**Status: unverified, and more permissive than the text recorded below.** The agreement PDF sits behind the download form and could not be fetched on 2026-10-03; Yelp's dataset page itself says only that the data is "intended for educational use". The July 2023 reading in this record differs on points that matter for a hosted demo: "academic use" is defined by who you are (§1, §3), no displaying Data to third parties (§4A) names reviews explicitly, aggregate disclosures are limited to academic purposes (§4E), and findings go to Yelp for review before any public presentation (§3). The three guardrails above are consistent with those clauses and are adopted as minimum constraints (free, no raw data in the repo or on the site, attribution), but they are not shown to be sufficient.

So nothing changes in the plan yet: the hosted demo with real Yelp data stays no-go and Yelp use stays private. **At the first Yelp download, read the agreement shown there, and check specifically (a) the definition of academic use for someone with no institution, (b) whether §4A allows showing derived scores or review text publicly, and (c) the §3 review requirement.** The assistant raises this again before touching Yelp. The API built in decision 0017 exposes no Yelp fields, so a public non-Yelp demo of the census is not blocked by any of this.

## What the agreement says (paraphrased, with section numbers)

| § | Clause | Effect on TableMap |
|---|---|---|
| 1, 3 | Data is for an academic project "as part of an ongoing course of study". "Academic use" means use by registered nonprofits, government, educational institutions or think tanks, and it must be not-for-profit **or** not intended to produce works for commercial use. Anything else needs Yelp's written consent. | A personal portfolio aimed at job applications sits in a gray zone. Eligibility depends on being affiliated with an educational institution and on how the work is framed. |
| 3 | Before any **public presentation or publication** of results involving the Data or the Yelp name, findings must be submitted to Yelp for review. Yelp commits to approve within 5 business days. | The README, blog post and video all need a pre-publication submission. |
| 4A | No displaying, performing or distributing any Data to third parties. Reviews and other user content are called out explicitly. | The demo video, screenshots, hosted demo and any cited review text on a public page are out without consent. |
| 4B, 4F | No commercial use. No use that competes with Yelp. | A public restaurant recommender is arguably competitive. |
| 4D | No sharing or making the Data available to any third party. | **Sending review text to Jev (hosted API) or to a rented GPU host may count.** Needs a decision before Week 4. |
| 4E | No disclosing summaries or metrics about the Data to third parties, except as needed for academic purposes (such as academic articles). | Blog and README metrics are fine only if they count as academic disclosure. Safest path is §3 review plus written consent. |
| 4I | No modifying, rating, ranking or commenting on content in the Data. | Probably aimed at responding to reviews on Yelp, but "rank every restaurant" is close enough to ask about. |
| 5 | Derivative works belong to Yelp. | Derived tables (`aspect_score`, `rating`, chunks, embeddings) are treated as Data. They can't be published either. |
| 10 | 12-month term from download. Yelp can terminate at will. On termination, delete all Data and copies. | Repo and results must survive losing the data. Budget for a re-download after Oct 2027. |

## Decision (proposed)

1. **Build privately and locally.** Weeks 1 to 8 proceed as planned, treating all Data and derived tables as private. Nothing derived from reviews is committed or published.
2. **Ask Yelp for written consent now**, scoped to: public code repo, write-up with aggregate metrics, a demo video, and processing by third-party services (Jev, rented GPU). Draft below. Send in Week 1 so there is an answer before Week 4.
3. **Hosted demo (Phase 9): no-go** unless Yelp's written consent explicitly covers public display. Do not plan around it.
4. **Showcase fallback if consent is declined or unanswered by end of Week 2:**
   - Public repo contains code, schemas, docs and synthetic fixtures only.
   - README and blog report aggregate results only (no review text, no review or business IDs) and are submitted to Yelp under §3 before publishing.
   - Demo video shows the pipeline and UI with review text redacted or replaced by synthetic reviews. Only included if Yelp approves under §3.
5. **Third-party processing fallback:** if Yelp does not approve sending review text to Jev or rented GPUs, run aspect scoring and embeddings fully local (smaller local models) and report Jev on a small non-Data sample, or on synthetic reviews, so the cascade experiment still has a story.

## Plan changes that follow

- **CI (Week 8):** a public repo's CI can't contain the Data. Run evals in CI against synthetic fixtures, and run the real-data evals locally or in a private repo.
- **Labeled set and eval sets** contain review text, so they stay private. Publish the labeling guidelines and the scripts that build them.
- **Repo hygiene:** `data/` and any DB dumps are gitignored from the first commit. Add a pre-commit check that blocks files over a size threshold and anything under `data/`.
- **Attribution:** never imply Yelp endorsement (§4G, 4K, 9). Use a neutral name and do not use Yelp branding in the UI or video.

## Open items

- [ ] Confirm eligibility: is this project being done under a UW affiliation or course? (Changes how §3 "academic use" reads.)
- [ ] Re-read the agreement shown at download time and note any changes from the July 2023 version.
- [ ] Send the consent email (draft below) and log the date and reply here.
- [ ] Decide the Jev question (§4D) before Week 4.

## Draft email to Yelp (not sent)

> To: dataset@yelp.com
> Subject: Written-consent request: portfolio project using the Yelp Open Dataset
>
> Hello,
>
> I'm using the Yelp Open Dataset (Philadelphia restaurants) for a non-commercial portfolio project on aspect-level review analysis and retrieval-augmented question answering. I'd like to confirm that the following are acceptable, or request written consent where they are not:
>
> 1. Publishing the source code publicly, without any Yelp Data or derived data.
> 2. Publishing a write-up with aggregate evaluation metrics (for example model accuracy and retrieval recall), with no review text and no business or review identifiers.
> 3. A short demo video of the application. I can use redacted or synthetic review text if displaying real reviews isn't allowed.
> 4. Processing review text with third-party services (a hosted classification API and rented GPU compute), which I can avoid by running locally if that is not allowed.
>
> I will submit the write-up and video for review under Section 3 before publishing. I will not use Yelp branding or imply endorsement.
>
> Thank you,
> [name], [affiliation]
