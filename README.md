# Steam-Aware Scheduling & Smart Valve Control for Tyre Curing

## Overview

Solid tyre manufacturing relies on **curing presses** that use steam to harden rubber in a hot mould. Steam is wasted on the factory floor in two distinct ways:

1. **Demand peaks** — several presses heating at once spike steam demand, causing boiler pressure dips and extra fuel burn to compensate.
2. **Idle waste** — valves left open on presses with no active job (between batches, during breaks, or breakdowns) because closing them depends on an operator remembering to do it.

This project builds a **schedule-aware valve controller** that smooths demand peaks and automatically shuts off idle valves — cutting wasted steam without slowing production.

## 📌 Project Architecture & Miro Board Links

- **Miro Interactive Architecture Board**: [Miro Board: Tyre Curing Digital Twin](https://miro.com/app/board/uXjVH5QDJAs=/)
- **Notion Integration**: Copy the URL `https://miro.com/app/board/uXjVH5QDJAs=/` and use `/miro` or `/embed` inside Notion to view the live board.

## Goal

Demonstrate that a schedule-aware valve controller can reduce wasted steam — both from presses heating simultaneously and from valves left open on idle presses — while still reaching the required curing temperature. This is a **lab-scale simulation and prototype**, not a production control system.

## Problem Context

- A single boiler feeds steam to multiple presses via a shared pipeline; valve control in Sri Lankan factories today is **manual**.
- The curing press cycle has distinct stages: **ramp → cure → cool → idle**.
  - The **ramp stage** has the highest steam demand, since temperature must rise before curing begins.
  - The **curing stage** needs lower but precise steam to hold temperature.
- This project targets **solid tyres** (e.g. "Solid-Tec"), not standard pneumatic tyres. Solid tyres are fully filled (no bladder) and cure far longer (~6–7 hours vs. minutes for pneumatic), which means lower operator attention and greater risk of inefficiency. Target curing temperature is approximately **130°C**.
- **Demand spikes**: simultaneous ramping across presses causes pressure/temperature drops, forcing the boiler to burn more fuel.
- **Idle waste trade-off**: cutting steam during idle risks a temperature drop that costs extra energy to recover on the next ramp; keeping steam on during idle is also wasteful. There is no simple existing solution to this trade-off.
- As a directional benchmark, comparable work in steam optimization reports **10–20% lower boiler fuel use and 15–25% lower CO₂** — if even a fraction of that transfers to tyre curing, the case for this project is strong.

## How It Works

The controller tracks two things at all times: **target curing temperature** and **the production schedule**.

- When multiple presses need to heat, it **staggers and softens valve ramp-ups** to avoid simultaneous peaks.
- When a press has no job (finished, waiting, stopped), it **closes the valve immediately** — no operator dependency.
- Controlling **boiler pressure** is preferred over direct temperature control, since pressure is easier to manage in a vessel and temperature can be derived from it.
- The scheduling engine itself is handled upstream; this system receives the production schedule as an input rather than generating it.

### System Architecture

![System Architecture](architecture_block_diagram.png)

## System Components

| # | Component | Description |
|---|-----------|--------------|
| 1 | Curing-press digital twin | Software model of a press: temperature profile, steam demand, valve position, and heating/holding/cooling/idle stages. Supports multiple presses running simultaneously. |
| 2 | Smart valve control logic | Decides valve opening based on temperature, schedule, and curing status. Auto-closes valve when idle. |
| 3 | Schedule integration | Reads a production schedule (CSV/JSON) so the controller knows what each press should be doing — and when it should be idle. |
| 4 | Edge prototype + dashboard | ESP32 / Raspberry Pi with simulated valve output, plus a dashboard showing steam use, temperature, and steam saved. |

## Deployment Plan (Factory-Side, Phased to De-Risk)

1. Deploy only temperature sensors first; monitor remotely (Wi-Fi/GSM gateway) for ~5 days to build a real temperature profile.
2. Add valve control to one mould after validating the sensor phase.
3. Expand progressively, addressing edge cases and anomalies along the way.

## Testing Plan

Run the simulator under ordinary control vs. smart control and compare steam use:

- **Peak test** — multiple presses heating together; smart control should give a lower, smoother steam peak while still hitting target temperature.
- **Idle test** — a press finishes with no next job; compare valve-left-open vs. auto-close, and measure steam saved.
