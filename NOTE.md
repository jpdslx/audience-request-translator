# Note: Parts 1 to 3, and how I used AI

## Part 1: Prioritise and diagnose

### What I'd automate first

1. **Audience definition (stage 2).** This is the largest high-risk work I can build without production access. Today a manager turns a loose request into criteria, then waits on Analytics for a query and a count. A tool that applies consent and exclusions in code removes both the wait and the risk. When a request is unclear, it asks the manager the questions that usually take a round of back-and-forth, so it also covers the audience part of brief intake (stage 1). It starts as a suggestion the manager approves. This is the MVP I built.
2. **QA (stage 6).** The rules already exist and almost all of them can be checked in code. Automating it also makes the next steps safe: once QA runs on every campaign, AI-written copy and translations get checked before anything goes out. In the Option A package, the missing consent filter for Portugal, the German text in the Spanish email and the wrong price would all have been caught.
3. **Reporting and learnings (stage 9).** The output stays inside the team, which makes it a safe place to prove the tools work before they touch anything customer-facing. Managers know their own campaigns, so they can check an automated report against what they expect and see quickly whether the tool gets it right. Each report that matches what they would have pulled themselves builds confidence in the tools that follow, including the ones that touch customers.

### What I'd deliberately leave manual

- **Approval (stage 7).** Someone has to own the decision that a campaign goes out. I'd automate the approval pack and the reminders, and leave the sign-off with the people accountable for it.

### The estimate I'd check first

**Ad-hoc requests (15 hours).** It's the largest number and the least defined: we don't know the volume, the types of request or the output people expect. My working assumption is that part of it is follow-up from other stages, for example a count someone didn't trust and asked to have checked. If that's right, getting audience definition right also reduces ad-hoc work.

To check it, I'd start with what already exists (the request channel or the Analytics queue for the last month or two). Then I'd ask each manager to log ad-hoc requests for two weeks: who asked, what for, time spent, and whether it was a follow-up to something they'd already received. Two weeks of real entries show the volume, the types of request and how much is follow-up. That tells us what's worth automating there, and whether better audience definition is already bringing it down.

### What I'd ask in my first week

**CRM managers**
1. *Walk me through your last campaign from request to send. Where did you wait, redo something, or catch a mistake late?*
   One real example tells me more than an estimate, including how much of the time is waiting.
2. *Can you forward me your last 10 audience requests? How long did each take, and did any need a follow-up because the first answer wasn't enough or didn't look right?*
   Real requests become test cases for the tool, and the follow-ups show how much ad-hoc work is really re-checking.
3. *What would a tool have to show you before you'd send to its audience without re-checking it yourself?*
   This lets the team define what trust looks like, and it shapes both the output and the rollout.

**Tech**
1. *Where do consent and customer data come from, how fresh are they in SFMC compared with the main database, and is there one source of truth for consent?*
   Consent is the highest-risk rule. In the case data, 31 people have duplicate records that disagree on their latest email consent, so I'd want to know which source wins before trusting any count.
2. *What access can a tool get (read-only database, SFMC API, a test environment), and who approves it?*
   This decides what can be built, and in what order.
3. *Where does audience logic live today (SFMC, the main database, Analytics scripts), and who maintains it?*
   In the case data, "app user" could mean an app flag or real app activity (125 customers have the flag but no app activity), and terms like "high-value" have no definition. The tool has to use the definitions the team already works with, so I need to know where they live and who owns them.

## Part 2: Why Option B

I chose Option B for two reasons.
- **It covers more of the team's time.** Audience definition alone is 14 hours a week and high risk, and the tool also covers the audience part of brief intake. QA is 10 hours.
- **AI has a bigger role.** In Option A, most of the checks follow a written checklist, and AI plays a supporting part. In Option B, the core of the work is language: turning a loose, non-standard request into an exact list, and knowing when to ask or push back. That makes it a better showcase of how I work with AI. Claude reads the request, and code applies consent and exclusions so the rules hold every time, which is the split I'd use for the agents that follow.

## Part 3: Make it stick

### Trust and adoption
- **Start with their own requests.** The first test set is each manager's last 10 audience requests (my second question for the managers), compared with what Analytics delivered. The first thing they see is their own work answered correctly.
- **Start small and run side by side.** One or two of the managers who send the most audience requests use it alongside the current process for a few weeks. If the counts match, we widen it.
- **Show the working.** Every answer says who's in, how the count was reached and what it assumed, so a manager can check it immediately. Their answer to my third question for the managers decides what else it must show.
- **Fix it once, for everyone.** The tool lives in one shared repository, and the command fetches the latest version before each request, so every manager is on the same version. Each request is logged to a shared table (the request, Claude's reading, the answer and any change the manager made, with no customer data). Each week I review the corrections, turn each into a fixed meaning and a test, and every manager gets the fix on their next request. I tell the manager who raised it.

### Measuring that it works
Most of these measures come from the shared log above.
- **Correction rate (the main number):** the share of built audiences where the manager changed the tool's reading before approving, by type of request, reviewed weekly. During the side-by-side weeks I also compare its counts with what Analytics delivered for the same requests.
- **Rule errors:** the tests run on every change, and Analytics re-counts consent and exclusions on a sample of approved audiences each month. The target is zero, and any miss stops the rollout.
- **Time:** request to approved audience, from the log's timestamps, compared with the two-week log from Part 1.
- **Usage and follow-ups:** requests in the tool's log against audience requests still going to Analytics, and the "was this a follow-up?" field from Part 1 to see whether "can you check this?" requests drop.

### From "suggests" to "acts alone"
The move is made per type of request, based on the correction rate, never for the whole tool at once.
1. **Suggests:** the manager approves every audience and Analytics spot-checks a sample.
2. **Builds on its own:** repeated requests that only use agreed definitions go straight to a finished audience, without a separate review of the count. The manager still approves the campaign before anything is sent, and anything new or unclear still gets questions.
3. **Acts alone:** for request types with a low correction rate over an agreed period, it pushes approved audiences to SFMC once there's API access.

### What I'd never fully automate
- **The decision that a campaign goes out** (stage 7). A person owns it.
- **Changes to the rules.** Consent, exclusions and what counts as a service message are set by Legal and the policy owners. The tool applies them and can't change them.
- **New business definitions.** What "high-value" or "lapsed" means is agreed by the team, then added to the tool.

## How I used AI

I built this with Claude Code. I worked through the brief and the data with it, and made the calls on scope, priorities and definitions (for example, which consent record wins when duplicates disagree). Claude wrote the code to those definitions.

Inside the tool, Claude only reads the request and picks from a fixed menu of filters. Code decides whether to build, ask or push back, applies consent and exclusions, and writes the query. Language is where AI helps most, and the rules need to give the same answer every time.

I didn't take the counts on trust. Each built audience is recounted a second way in plain Python, the tricky rules are tested on a small hand-made database, and I tested it live in Claude Code as a manager would. Those live tests shaped the changes listed in the README under "What testing changed".

Next, I'd run it on the managers' real requests and compare the results with what Analytics delivered. How often managers correct its reading decides when it moves from suggesting audiences to building them on its own (Part 3).
