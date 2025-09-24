#!/usr/bin/env python3
"""
Coverage checker script for JaCoCo XML reports.
Validates that code coverage meets the specified threshold.
"""

import sys
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

def parse_jacoco_xml(xml_file):
    """Parse JaCoCo XML report and extract coverage metrics."""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Initialize counters
        total_instructions_covered = 0
        total_instructions_missed = 0
        total_lines_covered = 0
        total_lines_missed = 0
        total_branches_covered = 0
        total_branches_missed = 0
        
        # Parse coverage data
        for counter in root.findall('.//counter'):
            counter_type = counter.get('type')
            covered = int(counter.get('covered', 0))
            missed = int(counter.get('missed', 0))
            
            if counter_type == 'INSTRUCTION':
                total_instructions_covered += covered
                total_instructions_missed += missed
            elif counter_type == 'LINE':
                total_lines_covered += covered
                total_lines_missed += missed
            elif counter_type == 'BRANCH':
                total_branches_covered += covered
                total_branches_missed += missed
        
        # Calculate coverage percentages
        instruction_total = total_instructions_covered + total_instructions_missed
        line_total = total_lines_covered + total_lines_missed
        branch_total = total_branches_covered + total_branches_missed
        
        instruction_coverage = (total_instructions_covered / instruction_total * 100) if instruction_total > 0 else 0
        line_coverage = (total_lines_covered / line_total * 100) if line_total > 0 else 0
        branch_coverage = (total_branches_covered / branch_total * 100) if branch_total > 0 else 0
        
        return {
            'instruction_coverage': instruction_coverage,
            'line_coverage': line_coverage,
            'branch_coverage': branch_coverage,
            'total_instructions': instruction_total,
            'total_lines': line_total,
            'total_branches': branch_total,
            'covered_instructions': total_instructions_covered,
            'covered_lines': total_lines_covered,
            'covered_branches': total_branches_covered
        }
        
    except ET.ParseError as e:
        print(f"❌ Error parsing XML file: {e}")
        return None
    except Exception as e:
        print(f"❌ Error reading coverage data: {e}")
        return None

def print_coverage_report(coverage_data):
    """Print a formatted coverage report."""
    print("\n📊 Coverage Report")
    print("=" * 50)
    print(f"Instructions: {coverage_data['covered_instructions']:,} / {coverage_data['total_instructions']:,} "
          f"({coverage_data['instruction_coverage']:.2f}%)")
    print(f"Lines:        {coverage_data['covered_lines']:,} / {coverage_data['total_lines']:,} "
          f"({coverage_data['line_coverage']:.2f}%)")
    print(f"Branches:     {coverage_data['covered_branches']:,} / {coverage_data['total_branches']:,} "
          f"({coverage_data['branch_coverage']:.2f}%)")
    print("=" * 50)

def check_coverage_threshold(coverage_data, threshold_percent, metric='line'):
    """Check if coverage meets the specified threshold."""
    if metric == 'line':
        actual_coverage = coverage_data['line_coverage']
    elif metric == 'instruction':
        actual_coverage = coverage_data['instruction_coverage']
    elif metric == 'branch':
        actual_coverage = coverage_data['branch_coverage']
    else:
        print(f"❌ Unknown coverage metric: {metric}")
        return False
    
    threshold_as_percent = threshold_percent * 100
    
    print(f"\n🎯 Coverage Quality Gate")
    print(f"Metric: {metric.title()} Coverage")
    print(f"Threshold: {threshold_as_percent:.1f}%")
    print(f"Actual: {actual_coverage:.2f}%")
    
    if actual_coverage >= threshold_as_percent:
        print(f"✅ Quality gate PASSED! ({actual_coverage:.2f}% >= {threshold_as_percent:.1f}%)")
        return True
    else:
        print(f"❌ Quality gate FAILED! ({actual_coverage:.2f}% < {threshold_as_percent:.1f}%)")
        gap = threshold_as_percent - actual_coverage
        print(f"   Need {gap:.2f}% more coverage to pass")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Check JaCoCo code coverage against quality gate threshold"
    )
    parser.add_argument(
        "xml_file",
        help="Path to JaCoCo XML report file (jacoco.xml)"
    )
    parser.add_argument(
        "threshold",
        type=float,
        help="Coverage threshold as decimal (e.g., 0.80 for 80%)"
    )
    parser.add_argument(
        "--metric",
        choices=['line', 'instruction', 'branch'],
        default='line',
        help="Coverage metric to check (default: line)"
    )
    parser.add_argument(
        "--verbose",
        action='store_true',
        help="Show detailed coverage information"
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not Path(args.xml_file).exists():
        print(f"❌ JaCoCo XML file not found: {args.xml_file}")
        return 1
    
    if not (0.0 <= args.threshold <= 1.0):
        print(f"❌ Threshold must be between 0.0 and 1.0, got: {args.threshold}")
        return 1
    
    print(f"🔍 Analyzing coverage report: {args.xml_file}")
    
    # Parse coverage data
    coverage_data = parse_jacoco_xml(args.xml_file)
    if coverage_data is None:
        print(f"❌ Failed to parse coverage data from: {args.xml_file}")
        return 1
    
    # Show coverage report
    if args.verbose or coverage_data['total_lines'] == 0:
        print_coverage_report(coverage_data)
    
    # Check if any code was found
    if coverage_data['total_lines'] == 0:
        print("⚠️  No code coverage data found. This might indicate:")
        print("   - No tests were executed")
        print("   - JaCoCo agent was not properly configured")
        print("   - No source code was instrumented")
        return 1
    
    # Check coverage threshold
    passed = check_coverage_threshold(coverage_data, args.threshold, args.metric)
    
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())