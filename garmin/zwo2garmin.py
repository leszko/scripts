"""Convert Zwift ZWO workout files and upload to Garmin Connect."""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from garminconnect import Garmin
from garminconnect.workout import (
    CyclingWorkout,
    ExecutableStep,
    RepeatGroup,
    WorkoutSegment,
)

STEP_TYPES = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
    "rest": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
}

TIME_CONDITION = {
    "conditionTypeId": 2,
    "conditionTypeKey": "time",
    "displayOrder": 2,
    "displayable": True,
}

POWER_TARGET = {
    "workoutTargetTypeId": 2,
    "workoutTargetTypeKey": "power.zone",
    "displayOrder": 2,
}

NO_TARGET = {
    "workoutTargetTypeId": 1,
    "workoutTargetTypeKey": "no.target",
    "displayOrder": 1,
}

CYCLING_SPORT = {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2}

PERCENT_UNIT = {"unitId": 253, "unitKey": "percent", "factor": 1.0}


def make_step(order: int, step_type: str, duration: int,
              power_low: float | None = None, power_high: float | None = None) -> ExecutableStep:
    target = POWER_TARGET if power_low is not None else NO_TARGET
    step = ExecutableStep(
        stepOrder=order,
        stepType=STEP_TYPES[step_type],
        endCondition=TIME_CONDITION,
        endConditionValue=float(duration),
        targetType=target,
    )
    if power_low is not None:
        step.targetValueOne = round(power_low * 100)
        step.targetValueTwo = round((power_high if power_high is not None else power_low) * 100)
        step.targetValueUnit = PERCENT_UNIT
    return step


def parse_zwo(zwo_path: str) -> dict:
    tree = ET.parse(zwo_path)
    root = tree.getroot()

    name = root.findtext("name", "Unnamed Workout")
    description = root.findtext("description")

    workout_el = root.find("workout")
    if workout_el is None:
        raise ValueError("No <workout> element found in ZWO file")

    steps = []
    order = 1
    total_duration = 0

    for element in workout_el:
        tag = element.tag
        duration = int(element.get("Duration", 0))

        if tag == "Warmup":
            low = float(element.get("PowerLow", 0.25))
            high = float(element.get("PowerHigh", 0.75))
            steps.append({"type": "warmup", "duration": duration, "power_low": low, "power_high": high})
            order += 1
            total_duration += duration

        elif tag == "Cooldown":
            low = float(element.get("PowerHigh", 0.25))
            high = float(element.get("PowerLow", 0.75))
            steps.append({"type": "cooldown", "duration": duration, "power_low": low, "power_high": high})
            order += 1
            total_duration += duration

        elif tag == "SteadyState":
            power = float(element.get("Power", 0.5))
            steps.append({"type": "interval", "duration": duration, "power_low": power, "power_high": power})
            order += 1
            total_duration += duration

        elif tag == "IntervalsT":
            repeat_count = int(element.get("Repeat", 1))
            on_dur = int(element.get("OnDuration", 30))
            off_dur = int(element.get("OffDuration", 30))
            on_power = float(element.get("OnPower", 1.0))
            off_power = float(element.get("OffPower", 0.5))
            steps.append({
                "type": "repeat",
                "repeat": repeat_count,
                "on_duration": on_dur, "off_duration": off_dur,
                "on_power": on_power, "off_power": off_power,
            })
            order += 1
            total_duration += (on_dur + off_dur) * repeat_count

        elif tag == "FreeRide":
            steps.append({"type": "interval", "duration": duration, "open": True})
            order += 1
            total_duration += duration

        elif tag == "Ramp":
            low = float(element.get("PowerLow", 0.25))
            high = float(element.get("PowerHigh", 0.75))
            steps.append({"type": "interval", "duration": duration, "power_low": low, "power_high": high})
            order += 1
            total_duration += duration

    return {
        "name": name,
        "description": description,
        "steps": steps,
        "total_duration": total_duration,
    }


def build_workout(parsed: dict) -> CyclingWorkout:
    garmin_steps = []
    order = 1
    for step in parsed["steps"]:
        if step["type"] == "repeat":
            repeat_steps = [
                make_step(1, "interval", step["on_duration"], step["on_power"], step["on_power"]),
                make_step(2, "recovery", step["off_duration"], step["off_power"], step["off_power"]),
            ]
            garmin_steps.append(RepeatGroup(
                stepOrder=order,
                stepType={"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
                numberOfIterations=step["repeat"],
                workoutSteps=repeat_steps,
                endCondition={
                    "conditionTypeId": 7,
                    "conditionTypeKey": "iterations",
                    "displayOrder": 7,
                    "displayable": False,
                },
                endConditionValue=float(step["repeat"]),
            ))
        elif step.get("open"):
            garmin_steps.append(make_step(order, step["type"], step["duration"]))
        else:
            garmin_steps.append(make_step(
                order, step["type"], step["duration"],
                step["power_low"], step["power_high"],
            ))
        order += 1

    return CyclingWorkout(
        workoutName=parsed["name"],
        description=parsed.get("description"),
        estimatedDurationInSecs=parsed["total_duration"],
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType=CYCLING_SPORT,
                workoutSteps=garmin_steps,
            )
        ],
    )


def main():
    parser = argparse.ArgumentParser(description="Convert ZWO workouts and upload to Garmin Connect")
    parser.add_argument("input", help="Path to ZWO XML file")
    parser.add_argument("--email", help="Garmin Connect email")
    parser.add_argument("--password", help="Garmin Connect password")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of uploading")
    parser.add_argument("--schedule", help="Schedule workout on date (YYYY-MM-DD)")
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    parsed = parse_zwo(args.input)
    workout = build_workout(parsed)

    if args.json:
        print(json.dumps(workout.to_dict(), indent=2, ensure_ascii=False))
        return

    email = args.email or os.environ.get("EMAIL")
    password = args.password or os.environ.get("PASSWORD")

    if not email or not password:
        print("Error: --email/--password or EMAIL/PASSWORD env vars required", file=sys.stderr)
        sys.exit(1)

    tokenstore = str(Path(__file__).parent / ".garmin_tokens.json")
    api = Garmin(email=email, password=password, prompt_mfa=lambda: input("Enter MFA code: "))
    api.login(tokenstore=tokenstore)
    api.client.dump(tokenstore)

    result = api.upload_cycling_workout(workout)
    workout_id = result.get("workoutId")
    print(f"Uploaded workout: {parsed['name']} (ID: {workout_id})")

    if args.schedule and workout_id:
        api.schedule_workout(workout_id, args.schedule)
        print(f"Scheduled for: {args.schedule}")


if __name__ == "__main__":
    main()
