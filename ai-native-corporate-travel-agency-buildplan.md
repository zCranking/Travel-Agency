# AI-Native Corporate Travel Agency — Build Plan
*Corporate/business travel · Hybrid model (owned brand + licensable tech) · Solo technical founder*
*Prepared July 2026*

---

## 1. The Strategic Thesis

Be honest about the terrain before writing a line of code: corporate travel is not an empty field. Navan is a public company (NASDAQ: NAVN) shipping an agentic assistant called Ava plus a consumer-style app called Edge. TravelPerk rebranded to Perk after acquiring Yokoy and shipped an assistant called Juno. BizTrip.AI (backed by Andrew Ng's AI Fund and, more recently, a minority investment from Sabre) is explicitly building "the leading agentic AI platform for enterprise" corporate travel. Otto the Agent (Madrona-backed) launched on top of Spotnana and Booking.com content. Amadeus just acquired an AI travel-assistant startup (SkyLink) to bolt onto its own stack. FCM relaunched an assistant called SAM. That's six well-funded players shipping agentic features in the same 12 months you'd be building your MVP.

This isn't a reason to avoid the space — the research consensus for 2026 (Bessemer, Gartner, Phocuswright) is that vertical AI agents win by taking a *narrow wedge* and going end-to-end on it, not by competing horizontally with incumbents on day one. A solo founder cannot out-fund Navan. You can out-focus them.

**The wedge that fits your answers (corporate travel + hybrid model + solo technical founder):** the underserved middle of the market — 20 to 500-employee companies that are too small for Navan/Amex GBT's enterprise sales motion (they want six-figure ACVs) and too complex for a pure self-serve OTA, so today they run travel on Brex/Ramp cards, group chats, and a spreadsheet. This segment is enormous, badly served, and — critically — it's the exact segment where a single founder + AI agents can deliver white-glove-feeling service without a call center, because the agents absorb the labor that used to require a bullpen of human agents.

**Why "hybrid" (own brand + licensable tech) is the right call, not just an available option:** you need real bookings, real disruptions, and real policy edge cases flowing through your system to make the agents good. You can't get that from a demo. So Phase 1–2 you *are* a boutique AI-native TMC serving a handful of SMB clients directly under your own brand — this is your R&D lab and your case-study machine. Once the core agent stack is proven on real trips, you package it as the thing other small TMCs, host agencies, and vertical SaaS platforms (fintechs, HR platforms, industry-specific software) license — exactly the "Travel-as-a-Service" pattern Spotnana pioneered at large scale, except you're building it lean and boarding it on top of Duffel instead of a GDS from day one.

---

## 2. Competitive & Infrastructure Landscape

| Player | What they are | Relevance to you |
|---|---|---|
| **Navan** | Public, agentic AI (Ava + Edge), massive funding | The incumbent you route around, not toward. Study their UX, don't compete on their turf (enterprise). |
| **Perk (formerly TravelPerk)** | Mid-market TMC + expense (Yokoy), assistant "Juno" | Closest analog to your target segment — watch their SMB/mid-market pricing and packaging closely. |
| **BizTrip.AI** | Early-stage, AI-Fund-backed, "agentic AI platform for enterprise" corporate travel, Sabre invested | Direct competitor in agent-native positioning; currently enterprise-leaning. |
| **Otto the Agent** | Madrona-backed, built on Spotnana + Booking.com content | Proof that "AI agent on top of Spotnana" is a viable architecture — validates part of your Phase 3 plan. |
| **Amadeus / SkyLink** | GDS incumbent acquiring AI-assistant capability | Signals GDS incumbents will keep buying/building agents; you won't out-content them, so don't try. |
| **Spotnana** | "Travel-as-a-Service" infrastructure — API-first platform for TMCs, fintechs, and tech companies to build travel products on (powers Brex Empower's travel) | This is the infrastructure model you'll graduate toward once you outgrow Duffel — and a plausible eventual partner or acquirer, not just a competitor. |

**Read this as:** the giants are racing to bolt AI onto legacy TMC infrastructure. Your advantage is being AI-native from line one, with zero legacy call-center cost structure, targeting the segment they're structurally incentivized to ignore.

---

## 3. Recommended Tech Stack

### 3.1 Agent orchestration layer — the core decision
- **LangGraph** for the production agent runtime. Across every 2026 framework comparison, the consensus is consistent: LangGraph is the most battle-tested for durable, stateful, multi-agent production systems (checkpointing, human-in-the-loop interrupts, explicit control flow instead of letting the LLM improvise routing — which also cuts token cost materially versus role-based frameworks). Companies like Klarna and Uber run production agents on it at scale.
- **CrewAI** as your *internal prototyping* tool only — fastest way to sketch a new agent role (e.g., "disruption-rebooking agent") in an afternoon before you formalize it as a LangGraph node. Don't ship CrewAI to production; use it to think.
- Model layer: stay **model-agnostic behind LangGraph** rather than hard-coupling to one vendor. Use Claude (Sonnet-class) as your default reasoning model for the booking/policy agents — strong at long tool-use chains and instruction-following on policy documents — and keep an escape hatch to swap models per node as pricing/quality shifts. Don't hand-roll a router; LangGraph handles this cleanly.
- **MCP (Model Context Protocol)** for tool wiring — it's become the de facto standard this year (150+ adopting organizations) and will let you plug in Duffel, your policy engine, and expense tools as discrete, swappable tools rather than bespoke integrations baked into agent code.

### 3.2 Travel content & booking layer
This is the single highest-leverage decision you'll make, because it determines your accreditation burden.

- **Duffel** for MVP and through Phase 2. It's a modern REST API covering 300+ airlines (GDS + direct NDC), 2M+ hotels, PCI compliance, and ticketing — and it does **not** require you to hold IATA/ARC accreditation, because Duffel/your host agency sits behind you as merchant of record. TravelPerk, Ramp, and Juni already build on it, which tells you it holds up for exactly your use case (fintech-adjacent, corporate-adjacent booking).
- Avoid **Amadeus Self-Service** for anything you build now — it's being sunset in favor of Amadeus Enterprise, which does push you toward needing IATA/ARC accreditation. Not worth the detour at MVP stage.
- **Graduate to Spotnana** (or a comparable GDS+NDC aggregation layer) once you're licensing the tech to other TMCs or need deep global corporate-rate/NDC content Duffel doesn't cover — this is a Phase 3–4 move, not a Phase 1 one. Spotnana is explicitly built to be white-labeled and embedded, which is exactly your hybrid-model endgame.
- **Host agency partnership** (not full ARC/IATA accreditation) is your accreditation strategy for Phase 1–2: you operate under an established host's IATA/ARC number, which gets you live in days/weeks instead of the 60–90 day, $20,000-surety-bond ARC process. Read the host agreement closely for what their E&O umbrella actually covers before assuming full protection.

### 3.3 Policy, memory & compliance layer
- **Postgres** (with **pgvector**) as your system of record — traveler profiles, negotiated rates, trip history, policy documents. Don't reach for a dedicated vector DB (Pinecone/Weaviate) until you've outgrown pgvector's performance envelope; for an MVP's document volume it won't be the bottleneck.
- **Retrieval layer** over each client's travel policy document (a PDF or Notion doc, realistically) so the policy agent can answer "is this in-policy" and "why" with citations back to the actual clause, not a hallucinated summary.
- **Duty-of-care module**: this is a genuine legal exposure area for your clients (ISO 31030:2021 is the operating standard; OSHA's General Duty Clause and EU Directive 89/391/EEC create the underlying legal obligation), and it's also a real product differentiator against spreadsheet-and-email travel management. Even a lightweight version — ingesting every PNR (managed and unmanaged), surfacing a "where are my people right now" view, and pushing destination risk alerts (a data feed like Riskline, or even a cheaper aggregator early on) — sets you apart from an OTA and legitimizes the "TMC" positioning with corporate buyers.

### 3.4 Application layer
- **Backend**: Python + **FastAPI**, since your agent stack (LangGraph) is Python-native — don't introduce a second language for the API layer.
- **Durable workflow engine**: **Temporal** for anything that spans hours/days without a human staring at it — monitoring a booked trip for schedule changes, waiting on an approval, retrying a failed ticketing call. LangGraph handles *within-conversation* state well; Temporal is the right tool for *long-running, resumable* background jobs (flight disruption watching, nightly re-shop for price drops). Don't over-engineer this in Phase 1 — a simple cron + queue (e.g., a Postgres-backed job table) is fine until you have real trips in flight; add Temporal when the reliability requirements justify it.
- **Frontend**: **Next.js + Tailwind**, chat-first UI (this is an AI-native product — the primary interface is conversational, with a traditional itinerary/dashboard view as the secondary "trust" surface travel managers will still want).
- **Payments**: Duffel handles PCI-compliant card payment for bookings out of the box. For company-level virtual cards/expense controls down the line, **Stripe Issuing** is the standard lean-startup choice (Lithic is the alternative if you need lower-level card-program control).

### 3.5 Observability & evaluation — do not skip this
Agent failures are multi-step and non-obvious; you will not catch "the agent booked the wrong fare class" or "the policy agent hallucinated a clause" from application logs alone.
- **Langfuse** (open-source, self-hostable, MIT-licensed, no seat pricing) as your default — it's the leading open-source option and it will keep working even as you outgrow it.
- **LangSmith** is worth adding specifically because you're on LangGraph — it has near-zero integration friction and purpose-built tracing for LangGraph's checkpointing/HITL model, and a generous free tier (5,000 traces/month) that covers you well past MVP.
- Build a small **eval set** of real booking/policy scenarios early (even 30–50 hand-written cases) and re-run it on every prompt or model change. This is the difference between "feels like it works" and actually knowing it works before a client's CFO finds the bug for you.

### 3.6 Infrastructure & DevOps
- **Fly.io or Railway** for MVP hosting (fast to deploy, cheap, good enough reliability for a pre-revenue product) — move to AWS/GCP only once a client's procurement team requires it.
- **GitHub Actions** for CI/CD.
- **Vanta or Drata** — don't buy this yet. See §5 for exactly when to start.

---

## 4. Phased Roadmap

### Phase 0 — Validate the wedge (2–4 weeks, before writing product code)
- Pick your specific sub-niche inside "corporate travel." Don't stay at "corporate travel" — go narrower: e.g., professional-services firms with frequent client-site travel, field-services/construction companies, or a vertical you have existing relationships in from your prior industry experience. Specificity is what lets a solo founder win.
- Get 5–10 real conversations with people who currently book travel for a company that size (often an office manager, EA, or founder — not a dedicated travel manager). You're listening for: what tool/process they use today, what breaks, what they'd pay to fix it.
- Try to get 1–2 **letters of intent** or a paid pilot commitment before you build anything non-trivial. This also becomes your first design partner.

### Phase 1 — MVP: single-agent booking + policy assistant (6–10 weeks)
- One LangGraph agent, tool-connected to Duffel, operating under a host agency's accreditation.
- Conversational flight + hotel search/booking with policy-aware recommendations (even a simple rules-based policy check counts at this stage — don't over-build the RAG policy layer yet).
- Human-in-the-loop by design: every booking above a threshold, or anything ambiguous, routes to *you* as the human fallback. You are the "agent supervisor" Navan's Ava has in software form — you're doing it manually, which is fine and expected at this stage.
- Ship this to your Phase-0 design partner(s) as a real, paid (even if discounted) pilot.

### Phase 2 — Multi-agent + duty of care (2–4 months)
- Split into specialized LangGraph nodes: search/booking agent, policy agent (now with real RAG over the client's actual policy doc), disruption/rebooking agent, and a lightweight duty-of-care/traveler-tracking view.
- Add Langfuse/LangSmith and your eval set — this is when reliability starts to matter because you have paying clients depending on it.
- Bring on 3–6 total SMB clients under your own brand. This is your case-study and reference-customer engine.

### Phase 3 — Package for licensing (4–6 months, can overlap Phase 2)
- Extract the agent stack behind an API/embeddable widget so another boutique TMC, host agency, or adjacent SaaS platform (expense tools, HR platforms, industry vertical software with a travel need) can license it — this is where your "hybrid" model pays off.
- Start SOC 2 Type 1 the moment a real prospect asks for it (see §5) — not before.
- Evaluate migrating/adding **Spotnana** as your content layer if you need GDS-depth global corporate content Duffel doesn't provide, or if a licensing partner requires it.

### Phase 4 — Scale
- SOC 2 Type 2, deeper NDC/GDS content, dedicated expense-platform integrations (Ramp/Brex/Concur), and a real enterprise sales motion once you have the logos and reliability data to support it.

---

## 5. Business, Legal & Compliance Checklist

- **Entity formation**: standard LLC/C-Corp depending on whether you intend to raise venture money later (C-Corp, Delaware, if yes).
- **Accreditation path**: host agency partnership (not direct IATA/ARC) for Phase 1–2. Get written confirmation of exactly what the host's E&O and compliance umbrella covers for you as a sub-agent — don't assume.
- **Seller-of-travel state registration**: required in several US states (California, Florida, Hawaii, Iowa, Washington, others) regardless of host-agency status — check per state you have clients in.
- **E&O insurance**: ~$500–2,000/year for a solo operation; get this even if your host agency claims coverage, and read the fine print.
- **Client fund handling**: never commingle client deposits/prepayments with operating funds — this is both a legal and a fraud-liability issue if a supplier defaults.
- **SOC 2**: don't start this pre-revenue or pre-prospect. The trigger is a real prospect sending you a security questionnaire, or you moving upmarket into mid-market/enterprise deal sizes. When that happens: go **Type 1** first (4–8 weeks with Vanta/Drata) to unblock the deal, then run the Type 2 observation window in parallel. Realistic first-year cost is $15–35K all-in for a lean scope.
- **Data privacy**: you'll be holding traveler PII (passport numbers, DOB, payment info) — treat this as sensitive from day one even before any formal compliance framework requires it; it's also just the right thing to do given who's in your database.

---

## 6. Path to Your First Client

Given your prior experience in the space, your unfair advantage is *not* generic cold outreach — it's your existing network.

1. **Mine your own network first.** Prior colleagues, former employers, people you know who run 20–200 person companies with real (even if informal) travel volume. This is faster and higher-conversion than any outbound campaign.
2. **Position as replacing pain, not selling AI.** The buyer doesn't care that you use LangGraph — they care that travel booking currently eats an EA's afternoon and nobody has visibility into where employees are when something goes wrong. Lead with that.
3. **Free or heavily discounted first pilot, in exchange for being a reference + real usage data.** You need the trip volume more than the first invoice.
4. **Show, don't pitch.** A live agent demo booking a real (or realistic sandboxed) trip against a real company policy document is a far stronger sales tool than a deck — build this as your standing asset early and keep it current as the product evolves.
5. **GBTA and regional business-travel-manager communities** are worth a presence in once you have a working product — this is where the people who evaluate TMCs actually congregate, and where "AI-native, built by someone who's actually worked in this space" is a real differentiator against faceless incumbents.
6. **After client #1–2**: turn them into case studies immediately (with permission), and start the Phase 3 licensing conversations with boutique host agencies or adjacent SaaS platforms who see what you built and want it themselves — this is the natural on-ramp to your hybrid model's second revenue line.

---

## 7. Honest Risk Notes

- This is a genuinely crowded, well-capitalized space right now — six credible AI-native or AI-augmented competitors shipped agentic features in the last year alone. Your edge is focus (a real sub-niche, not "corporate travel" broadly), speed (AI-native from day one, no legacy infra to carry), and founder-market fit (your prior experience). Don't try to out-fund or out-feature the incumbents — out-focus them.
- Duffel is the right MVP choice, but re-evaluate content depth by Phase 3 — some corporate negotiated-rate and complex international itinerary needs will outgrow it before you outgrow Spotnana-class infrastructure.
- Agent reliability in a domain with real financial and safety stakes (bookings, duty of care) is not optional polish — the observability/eval investment in §3.5 is what separates a demo from something a CFO will actually trust.
