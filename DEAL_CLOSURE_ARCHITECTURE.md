# Deal Closure Architecture & Data Flow

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        REAL ESTATE DEAL CLOSURE PIPELINE                     │
└─────────────────────────────────────────────────────────────────────────────┘

FRONTEND (Dashboard)
┌────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  Chart 1: Deal Closure Funnel          Chart 2: Booking Amount Tracking    │
│  ────────────────────────────────      ─────────────────────────────────   │
│  └─ Lead Count by Stage                 └─ Quoted vs Received              │
│     Site Visits    ─────┐ 8                                                │
│     Proposals      ────┐ 7              Lead Categorization               │
│     Follow-ups     ───┐ 5               ─────────────────────             │
│     Negotiating    ──┐ 2                • Proposals Sent: 7               │
│     Payments       ─┐ 2                 • Following Up: 5                │
│     Deals Closed   ┐ 1                  • Negotiating: 2                 │
│                                         • Awaiting Payment: 2             │
│                                         • Closed: 1                       │
│                                                                            │
│  Event Log Stream (Real-time)                                             │
│  ──────────────────────────────────────────────────────────────────────  │
│  12:15 PM | live_res_deal_001: send_proposal ₹95L booking amount        │
│  12:20 PM | live_res_deal_001: customer_follow_up (1/3)                 │
│  12:25 PM | live_res_deal_001: Response: POSITIVE                       │
│  12:26 PM | live_res_deal_001: send_payment_reminder                    │
│  ... [more events] ...                                                    │
└────────────────────────────────────────────────────────────────────────────┘
         ↑                                                  ↑
         │ Fetch metrics, categorization, events          │ Display results
         │                                                 │
┌────────┴─────────────────────────────────────────────────┴──────────────┐
│                       REST API Layer (app.py)                            │
│                                                                           │
│  GET /metrics/conversions      - Conversion funnel metrics              │
│  GET /lead-categorization      - Lead stage distribution                │
│  GET /simulate/live/stream     - Event stream (NDJSON)                  │
│  POST /metrics/reset           - Reset metrics                          │
│  POST /lead-categorization/reset - Reset categorization                 │
│                                                                           │
└────────┬──────────────────────────────────────────────────┬─────────────┘
         │                                                   │
         ↓                                                   ↓
┌────────────────────────────────────────────────────────────────────────┐
│                  Event Processing & Categorization                      │
│                      (_cache_call_stream in app.py)                     │
│                                                                          │
│  For each event:                                                         │
│  ├─ Track conversion metrics (total, contacted, interested, appt, closed)
│  ├─ Track market rates if property recommended                           │
│  └─ Categorize lead:                                                     │
│     ├─ eligible_for_contact     ← New contact needed                     │
│     ├─ scheduled_for_visit      ← Appointment scheduled                  │
│     ├─ following_up             ← In proposal/follow-up cycle            │
│     ├─ negotiating              ← In negotiation rounds                  │
│     ├─ awaiting_payment         ← Waiting for booking amount             │
│     ├─ cold_leads               ← Move to nurture                        │
│     └─ deal_closed              ← Closed with payment                    │
│                                                                          │
└────────┬───────────────────────────────────────────────────┬────────────┘
         │                                                   │
         ↓                                                   ↓
┌────────────────────────────────────────────────────────────────────────┐
│              Environment & State Management (env.py)                    │
│                                                                          │
│  Process Action ──→ Update Opportunity State ──→ Calculate Reward       │
│                                                                          │
│  Action Handlers:                                                        │
│  ├─ send_proposal              [UPDATE: proposal_sent, proposal_details]
│  ├─ customer_follow_up         [UPDATE: follow_up_count, responses]     │
│  ├─ send_negotiation_offer     [UPDATE: negotiation_round, offers]      │
│  ├─ send_payment_reminder      [UPDATE: payment_details]                │
│  ├─ process_booking_payment    [UPDATE: booking_amount_paid, date]      │
│  └─ finalize_deal              [UPDATE: deal_finalized, deal_closed]    │
│                                                                          │
└────────┬───────────────────────────────────────────────────┬────────────┘
         │                                                   │
         ↓                                                   ↓
┌────────────────────────────────────────────────────────────────────────┐
│         Agent Decision Logic & Action Generation (live_simulator.py)   │
│                                                                          │
│  observe() ──→ LiveTrafficAgent.choose_action() ──→ Action             │
│                                                                          │
│  Decision Tree Structure:                                               │
│  ├─ Classification phase (set category, priority)                       │
│  ├─ Qualification phase (collect missing info)                          │
│  ├─ Property recommendation phase                                       │
│  ├─ Customer contact phase                                              │
│  ├─ Site visit booking & completion phase                              │
│  ├─ PROPOSAL PHASE NEW ✓                                               │
│  │  └─ send_proposal → Formal proposal with booking amount            │
│  ├─ FOLLOW-UP PHASE NEW ✓                                             │
│  │  └─ customer_follow_up → Up to 3 follow-up rounds                  │
│  ├─ NEGOTIATION PHASE NEW ✓                                           │
│  │  └─ send_negotiation_offer → Up to 3 negotiation rounds            │
│  ├─ PAYMENT PHASE NEW ✓                                               │
│  │  ├─ send_payment_reminder → Send booking amount details            │
│  │  └─ process_booking_payment → Record payment received              │
│  └─ FINALIZATION PHASE NEW ✓                                          │
│     └─ finalize_deal → Mark deal as closed                            │
│                                                                          │
│  Each decision point evaluates:                                         │
│  • Opportunity state, stage, priority                                   │
│  • Customer responses & objections                                      │
│  • Business rules & SLAs                                                │
│                                                                          │
└────────┬───────────────────────────────────────────────────┬────────────┘
         │                                                   │
         ↓                                                   ↓
┌────────────────────────────────────────────────────────────────────────┐
│           Data Models & State Tracking (models.py)                      │
│                                                                          │
│  InboundLead ──→ OpportunityDetail ──→ [Enhanced with 20+ new fields]  │
│                                                                          │
│  OpportunityDetail fields for Deal Closure:                             │
│  ├─ Site Visit: site_visit_completed, site_visit_date, feedback        │
│  ├─ Proposal: proposal_sent, proposal_details, booking_amount_quoted   │
│  ├─ Follow-ups: follow_up_count, follow_up_dates, responses            │
│  ├─ Negotiation: negotiation_status, negotiation_round, offers         │
│  ├─ Payment: booking_amount_paid, booking_payment_date, method         │
│  └─ Finalization: deal_finalized, deal_closed_date, final_status       │
│                                                                          │
└────────┬───────────────────────────────────────────────────┬────────────┘
         │                                                   │
         ↓                                                   ↓
┌────────────────────────────────────────────────────────────────────────┐
│         Default Inventory & Test Leads (live_simulator.py)              │
│                                                                          │
│  DEFAULT_INVENTORY:                                                     │
│  ├─ res_prop_101: 2BHK Whitefield, ₹92L, cab available                │
│  ├─ res_prop_102: 3BHK Sarjapur, ₹1.18Cr, no cab                      │
│  └─ com_prop_301: Retail CBD, ₹3.15L/month                            │
│                                                                          │
│  DEFAULT_STREAM_LEADS: [5 original + 5 NEW for deal closure]           │
│                                                                          │
│  Original Test Leads:                                                   │
│  └─ live_res_001 through live_res_005 (diverse properties & budgets)   │
│                                                                          │
│  NEW Deal Closure Test Leads:                                           │
│  ├─ live_res_deal_001: Rohit Kumar (Quick Decision)                   │
│  ├─ live_res_deal_002: Kavya Desai (Hesitant Buyer)                   │
│  ├─ live_res_deal_003: Vikram Iyer (Negotiation)                      │
│  ├─ live_res_deal_004: Sneha Reddy (Ready to Buy)                     │
│  └─ live_res_deal_005: Anil Kapoor (Family Decision)                  │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Lead State Machine Diagram

```
                    RESIDENTIAL LEAD LIFECYCLE
                    ─────────────────────────

    ┌─────────────────────────────────────────────────────────────┐
    │                      LEAD RECEIVED                           │
    │  • Classification                                            │
    │  • Priority Setting                                          │
    │  • Property Recommendation                                   │
    └────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
                    ┌─────────────────────────────┐
                    │  CUSTOMER CONTACT PHASE     │
                    │  • Call Customer            │
                    │  • Confirm Property        │
                    │  • Confirm Site Visit      │
                    └────────┬────────────────────┘
                             │
                             ↓
                    ┌─────────────────────────────────┐
                    │  SITE VISIT BOOKED              │
                    │  • CAB Eligibility Check        │
                    │  • CAB Booking                  │
                    │  • Site Visit Scheduled        │
                    └────────┬────────────────────────┘
                             │
                             ↓
       ┌─────────────────────────────────────────────┐
       │                                             │
       │   ► SITE VISIT COMPLETED ◄ NEW STAGE       │
       │                                             │
       │   • Customer feedback collected             │
       │   • Property liked? YES → Next stage        │
       │                    NO  → Move to nurture    │
       │                                             │
       └────────┬─────────────────────────────────────┘
                │
                ↓
    ┌───────────────────────────────────────────────────┐
    │     ► PROPOSAL SENT ◄ NEW STAGE                  │
    │                                                   │
    │  • Calculate booking amount (7.5%)              │
    │  • Prepare payment plan                          │
    │  • Send formal proposal (Email/SMS/WhatsApp)    │
    │  • Timeline: 72 hours for decision             │
    │                                                   │
    └────────┬──────────────────────────────────────────┘
             │
             ↓
    ┌──────────────────────────────────────────────────────────┐
    │     ► FOLLOW-UP CYCLE (Up to 3) ◄ NEW STAGE             │
    │                                                          │
    │  FOLLOW-UP 1 (24-48 hrs after proposal)                 │
    │  ├─ Customer Positive   ────→ [Go to NEGOTIATION or PAYMENT]
    │  ├─ Customer Objection  ────→ [Go to NEGOTIATION]       │
    │  └─ No Response         ────→ [Go to FOLLOW-UP 2]       │
    │                                                          │
    │  FOLLOW-UP 2 (3-5 days after proposal)                  │
    │  ├─ Customer Positive   ────→ [Go to NEGOTIATION or PAYMENT]
    │  ├─ Customer Objection  ────→ [Go to NEGOTIATION]       │
    │  └─ No Response         ────→ [Go to FOLLOW-UP 3]       │
    │                                                          │
    │  FOLLOW-UP 3 (7-10 days after proposal)                 │
    │  ├─ Customer Positive   ────→ [Go to NEGOTIATION or PAYMENT]
    │  ├─ Customer Objection  ────→ [Go to NEGOTIATION]       │
    │  └─ No Response         ────→ [Move to NURTURE]         │
    │                                                          │
    └────────┬──────────────────────────────────────────────────┘
             │
             ├─────────────────────────┬──────────────────────┐
             │                         │                      │
             ↓                         ↓                      ↓
    ┌──────────────────┐    ┌──────────────────┐   ┌─────────────────┐
    │ PAYMENT-READY    │    │ NEGOTIATION      │   │ MOVE TO NURTURE │
    │ (Positive resp)  │    │ (Objections)     │   │ (No response)   │
    └────────┬─────────┘    └────────┬─────────┘   └─────────────────┘
             │                       │
             └───────────┬───────────┘
                         │
                         ↓
        ┌─────────────────────────────────────────────────────┐
        │   ► NEGOTIATION PHASE (Up to 3 rounds) ◄ NEW        │
        │                                                      │
        │  • Analyze customer objections                      │
        │  • Prepare counter-offer                            │
        │  • Send negotiation offer (Email/SMS)              │
        │  • Typical offer: 1-2L discount + extras           │
        │                                                      │
        │  ROUND 1: Send offer → Response?                    │
        │           ├─ Accept  → [Go to PAYMENT READY]       │
        │           ├─ Counter → [Go to ROUND 2]             │
        │           └─ Reject  → [Move to NURTURE]           │
        │                                                      │
        │  ROUND 2: Send offer → Response?                    │
        │           ├─ Accept  → [Go to PAYMENT READY]       │
        │           ├─ Counter → [Go to ROUND 3]             │
        │           └─ Reject  → [Move to NURTURE]           │
        │                                                      │
        │  ROUND 3: Send offer → Response?                    │
        │           ├─ Accept  → [Go to PAYMENT READY]       │
        │           └─ Reject  → [Move to NURTURE]           │
        │                                                      │
        └────────┬──────────────────────────────────────────────┘
                 │
                 ↓
        ┌──────────────────────────────────────────────────────┐
        │     ► PAYMENT REMINDER SENT ◄ NEW STAGE             │
        │                                                       │
        │  • Booking amount: ₹X (calculated)                 │
        │  • Payment deadline: 72 hours                        │
        │  • Payment methods: Bank/Check/Online               │
        │  • Send via: Email + SMS + WhatsApp                 │
        │  • Include: Invoice, beneficiary details, reference │
        │                                                       │
        │  Outcomes:                                           │
        │  ├─ Payment received in 48 hrs  → [Go to FINALIZE]  │
        │  ├─ Payment received in 72 hrs  → [Go to FINALIZE]  │
        │  └─ No payment by 72 hrs        → [Move to NURTURE] │
        │                                                       │
        └────────┬───────────────────────────────────────────────┘
                 │
                 ↓
        ┌──────────────────────────────────────────────────────┐
        │   ► BOOKING AMOUNT RECEIVED ◄ NEW STAGE             │
        │                                                       │
        │  • Payment verified in builder account              │
        │  • Generate receipt/confirmation                     │
        │  • Update booking reference                          │
        │                                                       │
        └────────┬───────────────────────────────────────────────┘
                 │
                 ↓
        ┌──────────────────────────────────────────────────────┐
        │       ► DEAL FINALIZED ◄ NEW STAGE                  │
        │                                                       │
        │  • Mark stage: "deal_closed"                        │
        │  • Record closing value: Full property price         │
        │  • Send booking agreement for signature             │
        │  • Assign project manager                           │
        │  • Set possession timeline                          │
        │  • Send congratulation message                      │
        │                                                       │
        │  ✅ SUCCESS - DEAL CLOSED                            │
        │  Revenue recognized                                 │
        │  Booking amount: ₹X received                        │
        │                                                       │
        └──────────────────────────────────────────────────────┘
```

---

## Data Flow by Action Type

```
ACTION: send_proposal
─────────────────────
Input:  opportunity state, budget, property details
        ↓
Process: • Calculate booking amount (7.5% of budget)
         • Prepare payment plan breakdown
         • Add possessions timeline, amenities
         ↓
Output:  Set opportunity fields:
         • proposal_sent = True
         • proposal_sent_date = now
         • proposal_details = {...plan details...}
         • booking_amount_quoted = amount
         ↓
Event:   Stream to dashboard
         Notify customer (Email/SMS/WhatsApp)


ACTION: customer_follow_up
──────────────────────────
Input:  opportunity state, follow_up_number, previous responses
        ↓
Process: • Increment follow_up_count
         • Simulate or fetch customer response
         • Categorize response (positive/objection/no_response)
         ↓
Output:  Set opportunity fields:
         • follow_up_count += 1
         • follow_up_responses.append(response)
         • last_follow_up_date = now
         ↓
Route:   Based on response:
         • Positive    → Send payment reminder
         • Objection   → Move to negotiation
         • No response → Check if follow-up_count < 3


ACTION: send_negotiation_offer
───────────────────────────────
Input:  customer objections, current offer, negotiation_round
        ↓
Process: • Analyze objections (price, terms, amenities)
         • Prepare counter-offer (discount, extras)
         • Increment negotiation_round
         ↓
Output:  Set opportunity fields:
         • negotiation_round += 1
         • customer_objections = [list]
         • negotiation_offers.append(new_offer)
         ↓
Event:   Stream to dashboard
         Notify customer with new offer


ACTION: send_payment_reminder
──────────────────────────────
Input:  booking_amount_quoted, customer contact info
        ↓
Process: • Prepare payment details
         • Calculate due date (72 hours)
         • Generate payment reference
         • Create payment link/instructions
         ↓
Output:  Set opportunity fields:
         • payment_details = {...complete...}
         • payment_due_date = now + 72 hours
         ↓
Event:   Notify via Email with invoice
         Notify via SMS with payment link
         Notify via WhatsApp with instructions


ACTION: process_booking_payment
────────────────────────────────
Input:  booking_amount_paid, payment_method, reference
        ↓
Process: • Verify payment amount matches expected
         • Verify payment method
         • Verify reference number
         ↓
Output:  Set opportunity fields:
         • booking_amount_paid = amount
         • booking_payment_date = now
         • booking_payment_method = method
         • booking_payment_reference = ref
         ↓
Reward:  50.0 (high - critical milestone)


ACTION: finalize_deal
─────────────────────
Input:  opportunity state (after payment received)
        ↓
Process: • Prepare booking agreement
         • Generate deal summary
         • Set project manager
         • Schedule possession timeline
         ↓
Output:  Set opportunity fields:
         • deal_finalized = True
         • deal_closed = True
         • deal_closed_date = now
         • stage = "deal_closed"
         • final_action_status = "success"
         ↓
Event:   Stream completion event
         Notify customer: Congratulations!
         Reward:  100.0 (maximum - deal closed!)
```

---

## Test Lead Journey Examples

```
QUICK DECISION LEAD: Rohit Kumar (live_res_deal_001)
────────────────────────────────────────────────────

Timeline: ~3 hours from site visit to deal closed

Day 1, 2:00 PM  | Site visit completed
                └─ Feedback: Very positive (likes project)
                
Day 1, 2:30 PM  | SEND PROPOSAL
                ├─ Booking amount: ₹7.125 L (₹95L × 7.5%)
                ├─ Payment plan attached
                └─ "Please confirm within 72 hours"
                
Day 1, 3:00 PM  | CUSTOMER FOLLOW-UP #1
                ├─ Agent: "Have you reviewed?"
                └─ Customer response: "YES - POSITIVE"
                
Day 1, 3:15 PM  | SEND PAYMENT REMINDER
                ├─ Amount: ₹7.125 L
                ├─ Due by: Day 1, 11:59 PM
                └─ Payment link: [https://...]
                
Day 1, 10:00 PM | BOOKING AMOUNT RECEIVED
                ├─ Payment: ₹7.125 L transferred
                └─ Confirmed in builder account
                
Day 1, 10:30 PM | FINALIZE DEAL
                ├─ Deal status: ✅ CLOSED
                ├─ Stage: deal_closed
                └─ Message: "Welcome aboard! Booking agreement sent."
                
TOTAL CONVERSION TIME: ~8 hours


NEGOTIATION LEAD: Vikram Iyer (live_res_deal_003)
──────────────────────────────────────────────────

Timeline: ~7 hours (includes 2 negotiation rounds)

Day 1, 2:00 PM  | Site visit completed
                └─ Feedback: Interested but price concerns
                
Day 1, 2:30 PM  | SEND PROPOSAL
                ├─ Price: ₹92 L (budget ₹92L, asking ₹95L)
                ├─ Booking: ₹6.9 L
                └─ "Please review terms"
                
Day 1, 3:00 PM  | CUSTOMER FOLLOW-UP #1
                ├─ Agent: "Any questions?"
                └─ Response: "OBJECTION - Price too high by 3L"
                
Day 1, 3:15 PM  | SEND NEGOTIATION OFFER (Round 1)
                ├─ New price: ₹93.5 L (1.5L discount)
                ├─ New booking: ₹7 L
                ├─ Added: Extended 5-year warranty
                └─ Added: 1 extra parking spot
                
Day 1, 4:00 PM  | CUSTOMER FOLLOW-UP #2
                ├─ Agent: "What do you think of the offer?"
                └─ Response: "OBJECTION - Needs more discount"
                
Day 1, 4:15 PM  | SEND NEGOTIATION OFFER (Round 2)
                ├─ New price: ₹92 L (3L discount - max builder can go)
                ├─ New booking: ₹6.9 L
                ├─ Kept: Extended warranty + parking
                └─ Added: Free interior design consultation
                
Day 1, 5:00 PM  | CUSTOMER FOLLOW-UP #3
                ├─ Agent: "Final offer - does it work?"
                └─ Response: "POSITIVE - Acceptable"
                
Day 1, 5:15 PM  | SEND PAYMENT REMINDER
                ├─ Amount: ₹6.9 L
                ├─ Due by: Day 1, 11:59 PM
                └─ Payment link sent
                
Day 1, 9:00 PM  | BOOKING AMOUNT RECEIVED
                ├─ Payment: ₹6.9 L confirmed
                └─ Reference: DEAL003_BOOKING
                
Day 1, 9:30 PM  | FINALIZE DEAL
                ├─ Deal status: ✅ CLOSED
                ├─ Final price: ₹92 L
                └─ Message: "Deal finalized with negotiated terms!"
                
TOTAL CONVERSION TIME: ~7.5 hours (with negotiations)
NEGOTIATIONS COMPLETED: 2 rounds


HESITANT LEAD: Kavya Desai (live_res_deal_002)
───────────────────────────────────────────────

Timeline: ~20 hours (multiple follow-ups before commitment)

Day 1, 2:00 PM  | Site visit completed
                └─ Feedback: Interested but wants to compare
                
Day 1, 2:30 PM  | SEND PROPOSAL
                ├─ Budget: ₹1.15 Cr
                ├─ Booking: ₹8.625 L
                └─ "Reviewing other projects too..."
                
Day 2, 2:00 PM  | CUSTOMER FOLLOW-UP #1 (24 hrs later)
                ├─ Agent: "Have you reviewed?"
                └─ Response: NO RESPONSE
                
Day 3, 2:00 PM  | CUSTOMER FOLLOW-UP #2 (48 hrs later)
                ├─ Agent: "Still interested in property?"
                └─ Response: "POSITIVE - Comparing costs"
                
Day 3, 2:15 PM  | SEND PAYMENT REMINDER (After positive response)
                ├─ Amount: ₹8.625 L
                ├─ Due by: Day 3, 11:59 PM
                └─ "Please confirm by EOD"
                
Day 3, 5:00 PM  | BOOKING AMOUNT RECEIVED
                ├─ Payment: ₹8.625 L transferred
                └─ After 40 minutes - quick decision!
                
Day 3, 5:30 PM  | FINALIZE DEAL
                ├─ Deal status: ✅ CLOSED
                └─ Message: "Congratulations! Welcome!"
                
TOTAL CONVERSION TIME: ~27 hours (longer due to comparison phase)
LEAD BEHAVIOR: Hesitant, but committed once clear decision made
```

---

## Integration Checklist

```
Implementation Phases:
──────────────────────

✅ PHASE 1: Models & Data Structures (DONE)
   ├─ [✓] Add 20+ new fields to OpportunityDetail
   ├─ [✓] Add 6 new action types
   └─ [✓] Extend Action class with new fields

✅ PHASE 2: Agent Logic (DONE)
   ├─ [✓] Extended LiveTrafficAgent decision tree
   ├─ [✓] Add proposal sending logic
   ├─ [✓] Add follow-up cycle logic
   ├─ [✓] Add negotiation handling logic
   └─ [✓] Add payment & finalization logic

✅ PHASE 3: Test Data (DONE)
   ├─ [✓] Create 5 diverse test leads
   ├─ [✓] Quick decision buyer
   ├─ [✓] Hesitant buyer
   ├─ [✓] Negotiation buyer
   ├─ [✓] Ready-to-buy customer
   └─ [✓] Family decision buyer

⏳ PHASE 4: Environment Handlers (TODO - NEXT)
   ├─ [ ] Implement send_proposal handler
   ├─ [ ] Implement customer_follow_up handler
   ├─ [ ] Implement send_negotiation_offer handler
   ├─ [ ] Implement send_payment_reminder handler
   ├─ [ ] Implement process_booking_payment handler
   └─ [ ] Implement finalize_deal handler

⏳ PHASE 5: Dashboard Integration (TODO)
   ├─ [ ] Add deal closure funnel chart
   ├─ [ ] Add booking amount tracking chart
   ├─ [ ] Add follow-up effectiveness metrics
   ├─ [ ] Add negotiation analytics
   └─ [ ] Display payment status

⏳ PHASE 6: Notifications (TODO)
   ├─ [ ] Email: Proposals, payment reminders, agreements
   ├─ [ ] SMS: Quick alerts, payment due notices
   └─ [ ] WhatsApp: Rich media proposals

⏳ PHASE 7: Database (TODO)
   ├─ [ ] Create proposals table
   ├─ [ ] Create follow-ups table
   ├─ [ ] Create negotiations table
   └─ [ ] Create payments table

⏳ PHASE 8: Testing & Validation (TODO)
   ├─ [ ] Run full stream with test leads
   ├─ [ ] Verify stage transitions
   ├─ [ ] Check metric calculations
   └─ [ ] Validate event streaming
```

