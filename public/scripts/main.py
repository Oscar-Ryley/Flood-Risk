#!/usr/bin/env python3

import sys
import subprocess
from pathlib import Path
from datetime import datetime


def run_script(script_name: str, script_path: Path) -> bool:
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            check=True,
            cwd=script_path.parent
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {script_name} failed with exit code {e.returncode}")
        return False
    except Exception as e:
        print(f"Error: {script_name} failed with error: {e}")
        return False


def main():
    script_dir = Path(__file__).resolve().parent
    data_dir = script_dir.parent / "data"
    
    print("\n" + "=" * 80)
    print("FLOOD RISK EXPOSURE - DATA PROCESSING PIPELINE")
    print("=" * 80)
    print(f"Scripts directory: {script_dir}")
    print(f"Data directory: {data_dir}")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Ensure data directory exists
    data_dir.mkdir(parents=True, exist_ok=True)
    
    scripts_to_run = [
        ("1. Process Substations", script_dir / "process_substations.py"),
        ("2. Export Risk Substations", script_dir / "export_risk_substations.py"),
        ("3. K-Means Clustering", script_dir / "kmeans_clustering.py"),
        ("4. Sensitivity Analysis", script_dir / "sensitivity_analysis.py"),
    ]
    
    results = []
    
    for i, (script_name, script_path) in enumerate(scripts_to_run, 1):
        if not script_path.exists():
            print(f"Error: Script not found: {script_path}")
            results.append((script_name, False))
            continue
        
        print(f"\n{script_name}")
        success = run_script(script_name, script_path)
        results.append((script_name, success))
        
        if not success:
            print(f"Warning: {script_name} failed. Continuing with next script...")
    
    # Print summary
    print("\n" + "=" * 80)
    print("PIPELINE SUMMARY")
    print("=" * 80)
    for script_name, success in results:
        status = "PASSED" if success else "FAILED"
        print(f"{script_name}: {status}")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    print(f"\nTotal: {passed}/{total} scripts completed successfully")
    print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Exit with appropriate code
    all_passed = all(success for _, success in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
