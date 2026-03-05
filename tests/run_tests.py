#!/usr/bin/env python3
"""
Simple test runner that doesn't require pytest.
Run with: python run_tests.py
"""
import sys
from pathlib import Path

# Add repo root and custom_components to path
repo_root = Path(__file__).parent.parent  # tests/ -> repo root
custom_components_path = str(repo_root / "custom_components")
if custom_components_path not in sys.path:
    sys.path.insert(0, custom_components_path)
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Import test modules
from tests import test_power_tariff, test_estimation, test_holiday_evenings, test_reduction_factor, test_cost_increase

def run_test_class(test_class, class_name):
    """Run all test methods in a test class."""
    instance = test_class()
    methods = [m for m in dir(instance) if m.startswith('test_')]
    
    passed = 0
    failed = 0
    
    print(f"\n{class_name}:")
    print("=" * 60)
    
    for method_name in methods:
        try:
            method = getattr(instance, method_name)
            method()
            print(f"  ✓ {method_name}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {method_name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {method_name}: ERROR - {e}")
            failed += 1
    
    return passed, failed

def main():
    """Run all tests."""
    print("Running Peak Monitor Tests")
    print("=" * 60)
    
    total_passed = 0
    total_failed = 0
    
    # Test classes from test_power_tariff.py
    test_classes = [
        (test_power_tariff.TestHolidays, "TestHolidays"),
        (test_power_tariff.TestTimeUtils, "TestTimeUtils"),
        (test_power_tariff.TestConsumptionReduction, "TestConsumptionReduction"),
        (test_power_tariff.TestInternalEstimation, "TestInternalEstimation"),
        (test_power_tariff.TestEdgeCases, "TestEdgeCases"),
    ]
    
    # Test classes from test_estimation.py
    test_classes.append((test_estimation.TestInternalEstimation, "TestInternalEstimation (detailed)"))

    # Test classes from test_reduction_factor.py
    test_classes.append((test_reduction_factor.TestDailyReduction, "TestDailyReduction"))
    test_classes.append((test_reduction_factor.TestWeekendReduction, "TestWeekendReduction"))
    test_classes.append((test_reduction_factor.TestHolidayReduction, "TestHolidayReduction"))
    test_classes.append((test_reduction_factor.TestExternalReducedSensor, "TestExternalReducedSensor"))
    test_classes.append((test_reduction_factor.TestCustomReductionFactor, "TestCustomReductionFactor"))
    test_classes.append((test_reduction_factor.TestHourConsumptionAvailability, "TestHourConsumptionAvailability"))

    # Test classes from test_cost_increase.py
    test_classes.append((test_cost_increase.TestCostIncreaseNoIncrease, "TestCostIncreaseNoIncrease"))
    test_classes.append((test_cost_increase.TestCostIncreaseWithNewPeak, "TestCostIncreaseWithNewPeak"))
    test_classes.append((test_cost_increase.TestCostIncreaseNEquals1, "TestCostIncreaseNEquals1"))
    test_classes.append((test_cost_increase.TestCostIncreaseCustomPrice, "TestCostIncreaseCustomPrice"))
    test_classes.append((test_cost_increase.TestCostIncreaseWithReductionFactor, "TestCostIncreaseWithReductionFactor"))
    test_classes.append((test_cost_increase.TestCostIncreaseStartupBehavior, "TestCostIncreaseStartupBehavior"))
    
    for test_class, class_name in test_classes:
        passed, failed = run_test_class(test_class, class_name)
        total_passed += passed
        total_failed += failed
    
    # Run test functions from test_holiday_evenings.py
    print(f"\nHoliday Evening Tests:")
    print("=" * 60)
    
    test_functions = [
        test_holiday_evenings.test_trettondagsafton,
        test_holiday_evenings.test_julafton,
        test_holiday_evenings.test_nyarsafton,
        test_holiday_evenings.test_paskafton,
        test_holiday_evenings.test_midsommarafton,
        test_holiday_evenings.test_multiple_evenings,
        test_holiday_evenings.test_empty_list,
        test_holiday_evenings.test_partial_list,
    ]
    
    for test_func in test_functions:
        try:
            test_func()
            print(f"  ✓ {test_func.__name__}")
            total_passed += 1
        except AssertionError as e:
            print(f"  ✗ {test_func.__name__}: {e}")
            total_failed += 1
        except Exception as e:
            print(f"  ✗ {test_func.__name__}: ERROR - {e}")
            total_failed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print(f"TOTAL: {total_passed + total_failed} tests")
    print(f"PASSED: {total_passed}")
    print(f"FAILED: {total_failed}")
    print("=" * 60)
    
    return 0 if total_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
