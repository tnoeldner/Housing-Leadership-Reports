Technical Requirement Document: ASCEND UND Housing Performance System

1. Goal and Purpose

The primary goal of the ASCEND UND Housing Performance System is to transition Housing and Residence Life management from relationship-based to performance-based leadership. The system must provide a unified, objective, and transparent method for defining expectations and evaluating staff across six distinct positions, utilizing the "ASCEND" framework.

2. Core Logic and Framework

The entire application is based on two core components:

2.1. The ASCEND Pillars (6 Total)

The six pillars represent the core competencies evaluated in every role.

Pillar

Focus

A

Affinity & Community Building

S

Service Excellence & Support

C

Cultivating Equity & Inclusion

E

Empowering Learning & Growth

N

Navigating Discovery & Innovation

D

Dedicated & Driven

2.2. The Rating Scale (4 Levels)

All evaluation criteria must be measured using the following four-level scale:

Level

Description

1

Needs Improvement

2

Meets Expectations

3

Exceeds Expectations

4

Outstanding

Specific Rule: Rubrics must be specific to 6 defined position groups (RA, Custodian, Admin Support, RD, AD, Senior Leadership). The system must support storing and loading the specific text descriptions (criteria) for each of the 6 pillars at each of the 4 levels for all 6 position types.

3. Data Model (Firestore)

All data must be stored persistently using Google Firestore.

3.1. Authentication and User Pathing

The application must use the following global variables for initialization and authentication: __app_id, __firebase_config, and __initial_auth_token.

Authentication: Use signInWithCustomToken(__initial_auth_token) or fall back to signInAnonymously() if the token is unavailable.

Data Pathing (Private): All user-defined data (Staff, Evaluations) must be scoped to the manager's userId to ensure privacy and separation of staff directories.

Data Type

Firestore Path (Private)

Purpose

Staff Directory

/artifacts/{__app_id}/users/{userId}/staff

Directory of individuals evaluated by the current user.

Evaluations

/artifacts/{__app_id}/users/{userId}/evaluations

Historical performance scores and comments.

Rubric Templates

/artifacts/{__app_id}/users/{userId}/rubrics

Configuration storage for the 6 position rubrics.

3.2. Data Structures

The system requires three primary collections:

A. Staff Directory Document (staff-{staffId}):

{
  "staffId": "UUID",
  "name": "string",
  "positionId": "string (e.g., RA, Custodian, RD)", // Link to Rubric
  "supervisorId": "string (Current authenticated user ID)"
}


B. Rubric Template Document (rubric-{positionId}):

{
  "positionId": "string (e.g., RA)",
  "positionName": "string (e.g., Resident Assistant)",
  "pillars": [
    {
      "pillarLetter": "string (e.g., A, S, C...)",
      "pillarName": "string",
      "criteria": [
        {"level": 1, "description": "string (The behavioral requirement)"},
        {"level": 2, "description": "string"},
        {"level": 3, "description": "string"},
        {"level": 4, "description": "string"}
      ]
    }
  ]
}


Specific Rule: The application must contain the criteria for the 6 specified positions upon initial setup.

C. Evaluation Document (evaluation-{UUID}):

{
  "staffId": "string (linked to Staff Directory)",
  "evaluationDate": "timestamp",
  "evaluatorId": "string (Current authenticated user ID)",
  "pillarScores": [
    { "pillarLetter": "A", "score": "number (1-4)", "comments": "string (Mandatory)"},
    // ... S, C, E, N, D pillars
  ],
  "overallScore": "number (average of pillar scores)",
  "notes": "string (General evaluation notes)"
}


4. User Flows and Functionality

4.1. Setup and Configuration

Initialization: On first use, the system must confirm that all 6 required Rubric Template documents exist in Firestore. If they do not, the user must be prompted to input the criteria or the system loads default placeholder text based on the criteria defined in the conversation.

Display: The system must clearly display the current manager's userId on the UI.

4.2. Staff Management (CRUD)

Add Staff: Form allows entry of staff member name and selection of their positionId from the 6 available types.

View Staff: Display a list of all staff members managed by the current userId. List must include Name, Position, and latest Evaluation Score.

4.3. Evaluation Flow

Selection: User selects a staff member from the Staff Management list.

Rubric Load: The system automatically loads the correct Rubric Template based on the staff member's positionId.

Scoring: For each of the 6 ASCEND pillars (A-D):

The corresponding criteria for levels 1-4 must be visible.

The user must select a score (1, 2, 3, or 4).

Mandatory Rule: A written comment must be provided for each pillar score.

Completion: Calculate the overallScore (average of the 6 pillars) and save the complete Evaluation Document to Firestore.

4.4. Reporting and Review

Real-Time Requirement: The Staff Management list and any reports must listen for changes using Firestore's onSnapshot() capability to ensure real-time data visibility.

Staff History: When viewing a single staff member, display a graph or timeline showing their overallScore trend across all saved evaluations.

5. Visual and Technical Constraints

5.1. Visual Identity

Theme: Green and White (University of North Dakota colors).

Logo/Iconography: Incorporate the Ascending Hawk theme (using SVG or simple styling).

Tagline: "Elevating Service. Empowering Students." must be visible on the main dashboard.

5.2. Technical Constraints

Responsiveness: The layout must be fully responsive, avoiding fixed pixel widths to ensure usability on mobile and desktop devices.

Technology Stack: Must be implemented in a single, modern framework file (HTML/CSS/JS or React/Angular) as per platform guidelines.

No Alerts: Do not use alert() or confirm(). Use custom UI elements for user confirmation or notifications.

No Indexing: Avoid using Firestore's orderBy() function; client-side sorting must be used to prevent runtime index creation errors.