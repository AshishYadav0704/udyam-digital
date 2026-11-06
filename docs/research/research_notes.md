# Research notes - market, competitors, regulation, integrations, LLM options

Researched 2 November 2026 from public sources. Each line says whether it is **public information** (with source)
or **our inference**. Prices are list prices as published by the vendor or reported by the cited outlet; verify before
contracting. Nothing here is Airtel-internal information.

## 1. Market size
- Public: as of 30 June 2026, over 8.84 crore enterprises had registered on the Udyam Registration Portal and Udyam
  Assist Platform (Rajya Sabha reply reported by KNN, 20 Jul 2026) -
  https://knnindia.co.in/news/newsdetails/msme/over-884-crore-msmes-registered-on-udyam-platforms-mos-karandlaje
- The case study uses "6 crore+ MSMEs"; we keep the case's figure on slides and cite the newer Udyam count only as context.

## 2. Competitor landscape (Indian telecom-led MSME offers)
| Provider | What is public | Onboarding model visible publicly | Source |
|---|---|---|---|
| Airtel Business | "Airtel Office Internet" launched for small businesses with Google Cloud and Cisco: FTTH up to 1 Gbps, local/STD calling, add-ons such as static IP; plans from Rs 999; "one plan, one bill". 2026 annual base rentals reported: 200 Mbps Rs 11,988, 300 Mbps Rs 17,988, 1 Gbps Rs 47,988 (ex-GST). Airtel IQ is a CPaaS; Airtel says it is the first telco to act as a WhatsApp Business Service Provider; "Airtel IQ Reach" is a self-serve marketing platform designed for SMBs (Aug 2023). | Plan pages + enquiry; self-serve for IQ Reach | telecomtalk.info/airtel-office-internet-service-plans-starting-rs999/457691/ ; telecomlead.com/?p=128363 ; bharti.com press release (IQ Reach, 1 Aug 2023) ; airtel.in/iq |
| JioBusiness | Launched Mar 2021 for MSMBs: integrated fibre + voice + digital tools, plans Rs 901 to Rs 10,001/month; Jio said a small business spent Rs 15,000-20,000/month on connectivity and tools. 2026: "Business Broadband Max 801" (100 Mbps, 1,200 GB, JioMeet/JioAttendance); Rs 801 / Rs 1,001 plans with JioCloud storage, prices ex-GST. | "Register interest" -> a JioBusiness executive contacts the business; assisted sales and digital account management | businesstoday.in (Mar 2021) ; gizbot.com JioBusiness plans ; telecomtalk.info/?p=1005076 ; pc-tablet.com/?p=72921 |
| Tata Tele Business Services | Positions itself as 100% SMB-focused; portfolio spans SmartOffice broadband with collaboration tools, Smartflo cloud communications (incl. Smartflo Lite for small businesses), toll-free, Centrex; WhatsApp Business Platform added to Smartflo (2022); Google Workspace partnership (2022). | Consultative / partner-led (case studies, demos) | tatatelebusiness.com articles (Aug 2025) ; telecomtalk.info/?p=626372 ; globaldata TTML profile |
| Vi Business | "ReadyForNext" MSME programme (with Dun & Bradstreet), 2.0 in Jun 2023 with a digital self-evaluation tool and exclusive MSME offers; partnership with PayU (payments, Google Workspace, location tracking, cloud storage, mobile security). | Sign up on website or at a Vi retail store | MyVi press release 27 Jun 2023 ; telecomtalk.info/?p=725498 ; inc42.com Vi-PayU |
| ACT Fibernet (enterprise) | ACT Enterprise 1 Gbps packages Rs 5,999-10,999/month ex-GST | Enquiry-led | telecomlead.com/?p=128363 |

Our inference (not a claim about competitors' internal capabilities): in the public material we reviewed we did not find
a telco offering a conversational, multilingual advisor that assembles a multi-product, eligibility-checked bundle and
takes the owner through quote, KYC and order tracking in one session. Public offers are mostly fixed packages plus
enquiry forms or executive callbacks. That is the gap Udyam Digital targets.

## 3. Regulation that shapes the design
- **DPDP Act 2023 / DPDP Rules 2025.** Rules notified 13-14 Nov 2025. Rules 1, 2, 17-21 in force immediately;
  Rule 4 (Consent Manager registration) after one year; Rules 3, 5-16, 22-23 (notice, security safeguards, breach
  intimation, retention, etc.) 18 months after publication, i.e. from **13/14 May 2027**. Sources: mondaq.com
  (1708164, 1713500), storyboard18.com (14 Nov 2025), PIB backgrounder (17 Nov 2025).
  - Our implication: a pilot launched in 2026-27 sits *before* the core obligations bite, but we build to them now
    (itemised notice, purpose-specific consent, withdrawal, security safeguards, retention + deletion, grievance route)
    so the product does not need re-work in May 2027. We do not claim certification or legal compliance.
- **DoT business-connection KYC.** DoT replaced "bulk connections" with "business connections" (Aug 2023, effective
  1 Dec 2023): SIMs stay inactive until each end user completes KYC and their details match the list given by the
  authorised representative; end-user changes must be re-verified within 7 days (May 2024 instructions).
  Sources: medianama.com (May 2024), lexplosion.in, dot.gov.in/sites/default/files/20052024.pdf
  - Our implication: the KYC flow verifies the business + authorised signatory, and mobile lines carry an end-user
    KYC step before activation (shown in the tracker); the advisor never promises SIM activation before that.
- **GST on telecom services** stays 18% (SAC 9984) after the GST 2.0 rationalisation of 22 Sep 2025. Sources:
  taxclue.in/guide/gst-on-telecom ; busy.in (postpaid GST). The quote shows prices ex-GST plus an 18% estimate
  because the catalogue does not state whether its prices include tax.

## 4. Integrations - what is real, what is mocked
| Capability | Public / official route | Status in our prototype |
|---|---|---|
| GSTIN verification | GSTN "Search Taxpayer" public API, accessed through a licensed GST Suvidha Provider (GSP); returns legal name, trade name, status, address. (Vayana, IRIS, Quicko GSP docs) | **Mock adapter** on mock_gstin_registry.csv behind the same interface. No scraping of the GST portal. |
| Udyam verification | Udyam portal verification exists; programmatic verification is commonly offered by KYC aggregators (e.g. AuthBridge, Zoop). We did not find an official public Udyam API. | **Mock adapter** on mock_udyam_registry.csv. Production: aggregator contract or MoMSME arrangement. |
| DigiLocker (individuals) | Requester API (OAuth2/OIDC, "Meri Pehchaan"), registration through the API Setu partner portal; applications reviewed by a committee; no public test environment (didit.me summary of NeGD docs, Oct 2026). | Designed, not built: needs requester approval. UI shows it as "coming in pilot". |
| Entity Locker (businesses) | NeGD service for companies, MSMEs, startups; Requester API spec v1.0 (Oct 2024). | Designed, not built. Target for business-document pull. |
| eSign | Aadhaar-based eSign via CCA-empanelled eSign Service Providers (open API for Application Service Providers). | Designed, not built: needs an ESP contract. |

## 5. LLM provider options (list prices per million tokens, as reported Oct-Nov 2026)
| Option | Input | Output | Notes | Source |
|---|---|---|---|---|
| Anthropic Claude Haiku 5.5 (`claude-haiku-5-5`) | $0.10 | $0.50 | prompts <= 100K tokens; $0.50/$2.50 above; released 7 Oct 2026 | techenclave.com, apidog.com, letsdatascience.com (citing Claude pricing docs) |
| Anthropic Claude Sonnet 5.5 | $2.00 | $10.00 | higher capability tier | letsdatascience.com, mixed-news.com |
| Google Gemini 3.6 Flash | $0.75 | $3.75 | temporary rate through 31 Dec 2026, then $1.50/$7.50 | chatbase.co, pricepertoken.com |
| Google Gemini 2.5 Flash-Lite | $0.10 | $0.40 | budget tier | morphllm.com |
| OpenAI GPT-5.4 mini | $0.75 | $4.50 | small tier | mem0.ai, costbench.com |

Our inference: one advisor session is roughly 8-12 turns at about 1.5K input + 0.3K output tokens each, i.e. well
under 25K tokens. At small-tier prices that is a fraction of a rupee per session, against a historic CAC of
Rs 15,053, so model *price* is not the deciding factor. The deciding factors are Hindi/Hinglish extraction accuracy,
schema-valid tool calls, latency, and the data-processing terms. We could not call any external model API from the
build sandbox, so the final choice must be made by running `scripts/eval_advisor.py --provider` (held-out set in
`backend/tests/advisor_eval_set.json`; the offline extractor scores 94.0% of fields, see
`analysis/outputs/advisor_eval.md`) against each candidate. Default configuration: `LLM_PROVIDER=auto` uses the first
key it finds (Anthropic `claude-haiku-5-5`, then OpenAI, then Gemini); with no key, the offline rule-based extractor runs
alone.
