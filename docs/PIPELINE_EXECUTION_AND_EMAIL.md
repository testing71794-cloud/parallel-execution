# Kodak Smile Parallel Continue Pipeline

## Goal
This pipeline keeps the clean stage bar while allowing parallel execution and continuation after failures.

## Top-level stage behavior
- Fetch Code from GitHub
- Install Dependencies
- Execute Non Printing Flows
- Generate Excel Report for Non Printing
- Execute Printing Flows
- Generate Excel Report for Printing
- AI Failure Analysis + Smart Retry
- Archive Reports & Artifacts
- Finalize Build Result

## How continuation works
Each parallel branch is wrapped with catchError:
- the branch can fail
- Jenkins records the branch/stage failure
- the pipeline continues
- a .failed flag is created
- the final stage decides overall result

## Recommended mode
Use multi_agent_parallel for best stability.

## Final result behavior
- if any flow/device branch failed -> pipeline_failed.flag exists -> Finalize stage marks FAILURE
- if AI analysis fails but tests passed -> UNSTABLE
- otherwise -> SUCCESS
