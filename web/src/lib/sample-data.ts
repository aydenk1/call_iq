export type TranscriptSegment = {
  speaker: string;
  startSec: number;
  endSec: number;
  text: string;
};

export type CallOutcome = {
  status: "potential" | "lost" | "neutral";
  amount?: string;
  reason?: string;
};

export type ContactProfile = {
  name: string;
  phone: string;
  status: string;
  notes: string[];
  previousCallIds: string[];
};

export type CallRecord = {
  id: string;
  createdAt: string;
  durationSec: number;
  summary: string;
  impliedName?: string;
  externalNumber?: string;
  tags: string[];
  outcome?: CallOutcome;
  transcript: TranscriptSegment[];
  audio: {
    durationSec: number;
    previewProgress: number;
  };
  suggestedTasks: string[];
  contactProfile?: ContactProfile;
};

export const callRecords: CallRecord[] = [
  {
    id: "call-1024",
    createdAt: "2024-10-04T17:12:00Z",
    durationSec: 782,
    summary: "Pricing follow-up on the team plan with onboarding questions.",
    impliedName: "Jordan",
    externalNumber: "+1 310 555 0185",
    tags: ["Potential sale", "$500", "Follow-up requested"],
    outcome: {
      status: "potential",
      amount: "$500",
    },
    transcript: [
      {
        speaker: "Agent",
        startSec: 0,
        endSec: 24,
        text: "Thanks for hopping on. I saw your note about the team plan. Want to walk through pricing?",
      },
      {
        speaker: "Jordan",
        startSec: 24,
        endSec: 56,
        text: "Yes. We have eight reps and need to understand the annual discount if we commit this month.",
      },
      {
        speaker: "Agent",
        startSec: 56,
        endSec: 116,
        text: "Annual gets you 15 percent off and priority onboarding. The base team plan starts at five hundred.",
      },
      {
        speaker: "Jordan",
        startSec: 116,
        endSec: 168,
        text: "Okay. What does onboarding look like and how fast can we get the call sync set up?",
      },
      {
        speaker: "Agent",
        startSec: 168,
        endSec: 210,
        text: "We can get the API connected within a day and provide a checklist for the supervisors.",
      },
      {
        speaker: "Jordan",
        startSec: 210,
        endSec: 252,
        text: "Great. Send that checklist and we will decide by Friday.",
      },
    ],
    audio: {
      durationSec: 782,
      previewProgress: 0.36,
    },
    suggestedTasks: [
      "Send onboarding checklist",
      "Share annual discount pricing",
      "Schedule decision follow-up for Friday",
    ],
    contactProfile: {
      name: "Jordan Hale",
      phone: "+1 310 555 0185",
      status: "Ops lead, evaluating 8 seats",
      notes: [
        "Interested in annual contract",
        "Needs onboarding timeline",
      ],
      previousCallIds: ["call-1009"],
    },
  },
  {
    id: "call-1009",
    createdAt: "2024-09-29T14:42:00Z",
    durationSec: 521,
    summary: "Renewal review ended with a pause due to budget pressure.",
    impliedName: "Taylor",
    externalNumber: "+1 415 555 0112",
    tags: ["Lost sale", "Too expensive", "$200"],
    outcome: {
      status: "lost",
      amount: "$200",
      reason: "Too expensive",
    },
    transcript: [
      {
        speaker: "Agent",
        startSec: 0,
        endSec: 32,
        text: "Following up on renewal. Do you still have room in the Q4 budget?",
      },
      {
        speaker: "Taylor",
        startSec: 32,
        endSec: 68,
        text: "Not this quarter. Finance cut discretionary spend and we have to pause new tools.",
      },
      {
        speaker: "Agent",
        startSec: 68,
        endSec: 110,
        text: "Understood. Would a smaller seat count keep it active?",
      },
      {
        speaker: "Taylor",
        startSec: 110,
        endSec: 148,
        text: "Even scaled down it is too much right now. We can revisit in Q2.",
      },
      {
        speaker: "Agent",
        startSec: 148,
        endSec: 196,
        text: "Thanks for the transparency. I will follow up in March.",
      },
    ],
    audio: {
      durationSec: 521,
      previewProgress: 0.62,
    },
    suggestedTasks: [
      "Send pause confirmation email",
      "Add Q2 budget reminder",
      "Offer lightweight plan options",
    ],
    contactProfile: {
      name: "Taylor Reed",
      phone: "+1 415 555 0112",
      status: "Finance manager",
      notes: ["Budget freeze through Q1"],
      previousCallIds: [],
    },
  },
  {
    id: "call-0997",
    createdAt: "2024-09-18T19:05:00Z",
    durationSec: 934,
    summary: "Inbound discovery call on integrating call scoring with CRM.",
    impliedName: "Morgan",
    externalNumber: "+1 212 555 0147",
    tags: ["Inbound lead", "Needs demo", "$1000+"],
    outcome: {
      status: "neutral",
      amount: "$1000+",
    },
    transcript: [
      {
        speaker: "Agent",
        startSec: 0,
        endSec: 26,
        text: "Thanks for reaching out. Can you share the main workflow you want to improve?",
      },
      {
        speaker: "Morgan",
        startSec: 26,
        endSec: 72,
        text: "We want to score calls automatically and push insights into Salesforce for our managers.",
      },
      {
        speaker: "Agent",
        startSec: 72,
        endSec: 126,
        text: "That fits well. We can tag sentiment, track objections, and sync highlights into CRM fields.",
      },
      {
        speaker: "Morgan",
        startSec: 126,
        endSec: 182,
        text: "Great. We also need to handle multiple regions and languages.",
      },
      {
        speaker: "Agent",
        startSec: 182,
        endSec: 228,
        text: "We support multilingual models. A demo next week would help map your regions.",
      },
    ],
    audio: {
      durationSec: 934,
      previewProgress: 0.28,
    },
    suggestedTasks: [
      "Book demo for next week",
      "Confirm CRM fields for insights",
      "Share multilingual model coverage",
    ],
    contactProfile: {
      name: "Morgan Diaz",
      phone: "+1 212 555 0147",
      status: "Sales operations",
      notes: ["Needs Salesforce integration", "Multi-region rollout"],
      previousCallIds: [],
    },
  },
];
