from scenario import *

def menu():
    while True:
        print("\n--- Multi-Agent System Scenarios ---")
        print("1. Normal")
        print("2. Failure (Rooms Closed)")
        print("3. Tool Blocked")
        print("4. Preemption")
        print("5. Random Failure")
        print("6. Timeout")
        print("7. Rate Limit")
        print("8. Exit")

        c = input("Choice: ")

        if c == "1":
            scenario_normal()
        elif c == "2":
            scenario_rooms_closed()
        elif c == "3":
            scenario_tool_blocked()
        elif c == "4":
            scenario_preemption()
        elif c == "5":
            scenario_random_failure()
        elif c == "6":
            scenario_timeout()
        elif c == "7":
            scenario_rate_limit()
        elif c == "8":
            break
        else:
            print("Invalid choice")

if __name__ == "__main__":
    menu()
