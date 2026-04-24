#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 9:
        return 1
    rdir, did, dname, seg, flow, ec, mlog, junit = sys.argv[1:9]
    out = Path(rdir) / "atp_device_status.json"
    try:
        me = int(ec)
    except ValueError:
        me = -1
    out.write_text(
        json.dumps(
            {
                "deviceId": did,
                "deviceName": dname,
                "deviceSeg": seg,
                "flow": flow,
                "maestroExit": me,
                "logPath": mlog.replace("\\", "/"),
                "junitPath": junit.replace("\\", "/"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
