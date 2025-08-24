#!/usr/bin/env python3
"""
Test runner script for the Twitch Ollama Chatbot test suite.

This script provides various options for running tests including:
- Unit tests only
- Integration tests only
- Performance tests only
- All tests
- Coverage reporting
- Parallel execution
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print(f"\n✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {description} failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"\n❌ Command not found: {cmd[0]}")
        print("Make sure pytest is installed: pip install -r tests/requirements.txt")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run Twitch Ollama Chatbot tests")
    parser.add_argument(
        "--type", 
        choices=["unit", "integration", "performance", "all"],
        default="all",
        help="Type of tests to run (default: all)"
    )
    parser.add_argument(
        "--coverage", 
        action="store_true",
        help="Generate coverage report"
    )
    parser.add_argument(
        "--parallel", 
        action="store_true",
        help="Run tests in parallel"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip slow tests (performance tests)"
    )
    parser.add_argument(
        "--html-report",
        action="store_true",
        help="Generate HTML coverage report"
    )
    
    args = parser.parse_args()
    
    # Base pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add verbosity
    if args.verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")
    
    # Add parallel execution
    if args.parallel:
        cmd.extend(["-n", "auto"])
    
    # Add coverage
    if args.coverage:
        cmd.extend([
            "--cov=chatbot",
            "--cov-report=term-missing"
        ])
        
        if args.html_report:
            cmd.extend(["--cov-report=html:htmlcov"])
    
    # Determine which tests to run
    test_patterns = []
    
    if args.type == "unit":
        test_patterns = [
            "tests/test_database_manager.py",
            "tests/test_ollama_client.py", 
            "tests/test_content_filter.py",
            "tests/test_configuration_manager.py"
        ]
    elif args.type == "integration":
        test_patterns = [
            "tests/test_integration_message_flow.py",
            "tests/test_integration_chat_commands.py"
        ]
    elif args.type == "performance":
        if args.fast:
            print("⚠️  Skipping performance tests due to --fast flag")
            return True
        test_patterns = ["tests/test_performance.py"]
    else:  # all
        if args.fast:
            test_patterns = [
                "tests/test_database_manager.py",
                "tests/test_ollama_client.py", 
                "tests/test_content_filter.py",
                "tests/test_configuration_manager.py",
                "tests/test_integration_message_flow.py",
                "tests/test_integration_chat_commands.py"
            ]
        else:
            test_patterns = ["tests/"]
    
    # Add test patterns to command
    cmd.extend(test_patterns)
    
    # Add markers for performance tests
    if not args.fast and args.type in ["performance", "all"]:
        # Don't add any markers - run all tests including performance
        pass
    elif args.fast:
        # Skip performance tests
        cmd.extend(["-m", "not performance"])
    
    # Run the tests
    success = run_command(cmd, f"{args.type.title()} Tests")
    
    if success and args.coverage and args.html_report:
        print(f"\n📊 Coverage report generated in htmlcov/index.html")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)