# References and Research Register

**Verified means:** the URL was opened/returned as an official/publisher source in the first-pass research session on 2026-10-15. It does not mean CampusTwin has independently validated the product's marketing claims or conducted a systematic literature review. Product pages are used to understand existing categories/capabilities, not to claim third-party performance.

## 1. Existing product context (do not claim individual features are novel)

1. **Schneider Electric — Operations Management / EcoStruxure Building.** Official product page describes central monitoring/management of building systems, occupancy-based HVAC/lighting automation, analytics and maintenance prioritization. URL: https://www.se.com/in/en/work/software/ecostruxure-building/large-buildings-operations-management/ . Relevance: building systems already combine building controls and energy/operational visibility; CampusTwin must differentiate through its auditable evidence → approved intervention → independent verification → ledger story, without claiming those individual capabilities are unique.
2. **Schneider Electric — Energy Management.** Official building energy-management product information covers monitoring, analysis, controls, forecasts and energy-use visibility by load/building. URL: https://www.se.com/in/en/work/software/ecostruxure-building/large-buildings-energy-management/ . Relevance: establish comparable existing category; do not present dashboards or energy analytics as new inventions.
3. **Siemens — Desigo systems / building automation.** Official product family page describes monitoring/control of HVAC and other building systems and energy management. URL: https://www.siemens.com/en-us/products/desigo/ . Relevance: buildings already have integrated management/control platforms. CampusTwin is a hackathon operational prototype, not a substitute for a certified building automation system.
4. **Siemens — Desigo CC.** Official product page describes central integration/monitoring of HVAC, lighting, fire safety, security and building operations. URL: https://www.siemens.com/en-us/products/desigo/cc/ . Relevance: reinforces that integrated building monitoring is an established category.

## 2. Verification, calculation, and measurement practice

5. **U.S. Department of Energy, Federal Energy Management Program — M&V Guidelines: Measurement and Verification for Performance-Based Contracts Version 5.0 (published 2024-10-14).** https://www.energy.gov/cmei/femp/articles/mv-guidelines-measurement-and-verification-performance-based-contracts-version-0 . The guide concerns procedures for verifying/quantifying savings from energy-efficient equipment, water conservation, O&M, renewable energy and cogeneration. Design lesson: baseline, methods, assumptions, calculation, rates/factors and post-installation evidence should be explicit. CampusTwin's short virtual scenario check is not represented as compliance with this guide or as a validated real-world M&V method.
6. **U.S. DOE FEMP — Measurement and Verification for Federal Energy Savings Performance Contracts.** https://www.energy.gov/cmei/femp/measurement-and-verification-federal-energy-savings-performance-contracts . Describes M&V options and proportionality of verification effort to performance risk and expected savings. Design lesson: do not imply one simplistic method is adequate for every real-world claim.
7. **U.S. DOE FEMP — Measurement and Verification Activities Required in the ESPC Process.** https://www.energy.gov/cmei/femp/measurement-and-verification-activities-required-energy-savings-performance-contract . Discusses baseline/estimated savings, M&V plan, post-installation verification and reporting. Design lesson: retain baseline details, assumptions, sources, method and post-intervention evidence.

## 3. Trustworthy AI, privacy, API safety

8. **NIST — AI Risk Management Framework (AI RMF 1.0) resources.** https://airc.nist.gov/airmf-resources/airmf/ . Voluntary framework for incorporating trustworthiness considerations in AI design, development, use and evaluation. Design lesson: expose limitations, preserve traceability, evaluate failure and make human decision boundaries visible. This implementation does not claim formal NIST conformance.
9. **OWASP — API Security Top 10 (2023).** https://api-security.owasp.org/editions/2023/en/0x00-header/ . API security risk taxonomy. Design lesson: validate identifiers/inputs, restrict access where relevant, prevent unsafe API consumption, and keep sensitive details out of responses/logs. This does not imply the app has undergone a security audit.

## 4. Framework implementation references

10. **FastAPI — Testing.** https://fastapi.tiangolo.com/tutorial/testing/ . Official documentation describes testing APIs using pytest-compatible tests and TestClient. Relevance: route contract/integration tests.
11. **SQLAlchemy 2.0 — ORM documentation.** https://docs.sqlalchemy.org/en/20/orm/ . Official SQLAlchemy 2.0 ORM docs. Relevance: DB models, relationships, transaction handling, persistence.
12. **Vite — Getting Started.** https://vite.dev/guide/ . Official build/dev-server documentation; current page notes minimum Node requirements that must be checked against installed versions/templates. Relevance: clean install/build/preflight.
13. **React — Installation and project guidance.** https://react.dev/learn/installation . Official React setup guidance. Relevance: frontend setup and current recommended adoption path.

## 5. Source-use rules

- Record exact source titles/URLs, access dates, and the claim being supported.
- Research and product sources inform design choices but do not count as evidence of CampusTwin performance.
- Do not copy logos, proprietary assets, code, datasets, or model weights without compatible licensing/permission.
- If quoting product performance claims, preserve relevant conditions and methodology; prefer not to use them in the pitch.
- Add academic papers only after verifying title, authors, venue, year, DOI/URL, relevant evidence, and limitations against the publisher or repository.
- Do not claim novelty based on an incomplete literature search.
