import pandas as pd
from datetime import datetime


def read_csv(file_path):
    df = pd.read_csv(file_path)
    return df


def get_press_schedule(file_path, press_no="P001"):
    cycles = get_all_press_schedules(file_path, press_no)
    if cycles:
        return cycles[0]["start_in"], cycles[0]["start_out"]
    return None, None


def get_all_press_schedules(file_path, press_no="P001"):
    df = read_csv(file_path)
    press_df = df[df["Press No"] == press_no]
    cycles = []
    for _, row in press_df.iterrows():
        start_in_str = str(row["Start In"]).strip()
        start_out_str = str(row["Start Out"]).strip()
        tyre_id = str(row["Tyre ID"]).strip() if "Tyre ID" in row and pd.notna(row["Tyre ID"]) else f"{press_no}_T{len(cycles)+1}"
        start_in_time = datetime.strptime(start_in_str, "%Y-%m-%d %H:%M")
        start_out_time = datetime.strptime(start_out_str, "%Y-%m-%d %H:%M")
        cycles.append({
            "tyre_id": tyre_id,
            "start_in": start_in_time,
            "start_out": start_out_time
        })
    return cycles