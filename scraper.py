#!/usr/bin/env python3
"""
Google Calendar Countdown Timer
Scrapes Google Calendar events and starts macOS native timers before meetings.
"""

import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
import time
import re
import subprocess
import sys

# ============================================================================
# CONFIGURATION - Edit these values
# ============================================================================

# Chrome Profile Settings
# Find your profile: Open Chrome → chrome://version → Copy "Profile Path"
# Example: /Users/yourname/Library/Application Support/Google/Chrome/Default
CHROME_USER_DATA_DIR = "/Users/takumi.nishida/Library/Application Support/Google/Chrome"
CHROME_PROFILE_DIRECTORY = "Default"  # Usually "Default" or "Profile 1", "Profile 2", etc.

# Calendar Settings
CALENDAR_LOAD_WAIT = 3  # Seconds to wait for calendar to load

# ============================================================================


def setup_chrome_driver():
    """Configure Chrome with authenticated user profile."""
    import os
    import shutil
    import tempfile
    from pathlib import Path
    
    source_profile = Path(CHROME_USER_DATA_DIR) / CHROME_PROFILE_DIRECTORY
    
    # Create a temporary copy of the profile
    temp_dir = Path(tempfile.gettempdir()) / "chrome_calendar_profile"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    
    print(f"🔧 Copying Chrome profile: {CHROME_PROFILE_DIRECTORY}")
    print(f"📂 From: {source_profile}")
    
    # Copy only essential files for authentication (faster than full copy)
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_profile = temp_dir / "Default"
    temp_profile.mkdir(exist_ok=True)
    
    essential_files = ["Cookies", "Login Data", "Web Data", "Preferences"]
    for file in essential_files:
        src = source_profile / file
        if src.exists():
            dst = temp_profile / file
            try:
                shutil.copy2(src, dst)
                print(f"   ✓ Copied {file}")
            except Exception as e:
                print(f"   ⚠️  Could not copy {file}: {e}")
    
    options = Options()
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--headless=new")  # Run Chrome in headless mode (background)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-data-dir={temp_dir}")
    options.add_argument("--profile-directory=Default")
    
    print(f"🚀 Launching Chrome with copied profile...")
    
    try:
        driver = uc.Chrome(options=options)
        print(f"✅ Chrome launched successfully!")
        return driver
    except Exception as e:
        print(f"❌ Error launching Chrome: {e}")
        raise


def scrape_calendar_events(driver):
    """Scrape visible events from Google Calendar week view."""
    print("🌐 Navigating to Google Calendar...")
    try:
        driver.get("https://calendar.google.com/calendar/u/0/r/week")
        print("📅 Loaded Google Calendar with authenticated profile...")
        print(f"⏳ Waiting for calendar to load...")
        time.sleep(3)  # Initial load
        
        # Check current URL to see if we're logged in
        current_url = driver.current_url
        print(f"📍 Current URL: {current_url}")
        
        if "accounts.google.com" in current_url:
            print("⚠️  Not logged in! Chrome opened but you need to log in to Google.")
            print("💡 Make sure you're using a Chrome profile that's already logged into Gmail.")
            return []
        
        # Wait for calendar grid to load
        print("⏳ Waiting for events to render...")
        time.sleep(3)  # Extra time for events to render
            
    except Exception as e:
        print(f"❌ Error loading calendar: {e}")
        return []
    
    print("🔍 Searching for calendar events...")
    
    events = []
    
    try:
        # Look for event elements with data-eventid (actual scheduled events)
        # These appear in the time grid, not the all-day row
        event_chips = driver.find_elements(By.CSS_SELECTOR, "[data-eventid][role='button']")
        print(f"📋 Found {len(event_chips)} event elements with data-eventid")
        
        for chip in event_chips:
            try:
                aria_label = chip.get_attribute("aria-label")
                
                # If no aria-label, try to get inner text from XuJrye div
                if not aria_label:
                    try:
                        inner_div = chip.find_element(By.CLASS_NAME, "XuJrye")
                        aria_label = inner_div.text
                        if not aria_label:
                            print(f"   ⚠️  Skipped: no aria-label or inner text")
                            continue
                        print(f"   📝 Using inner text: {aria_label[:100]}...")
                    except:
                        print(f"   ⚠️  Skipped: no aria-label or inner text")
                        continue
                else:
                    print(f"   🔎 Checking aria-label: {aria_label[:100]}...")
                    
                # Skip working location entries
                if "working location" in aria_label.lower():
                    print(f"   ⏭️  Skipped: working location")
                    continue
                    
                # Skip all-day events (they say "All day" in the label)
                if "all day" in aria_label.lower():
                    print(f"   ⏭️  Skipped: all day event")
                    continue
                
                # Must have time indicators (like "1:30pm" or "10am")
                if not any(x in aria_label.lower() for x in ["am", "pm"]):
                    print(f"   ⏭️  Skipped: no am/pm time")
                    continue
                
                print(f"✅ Event found: {aria_label}")
                events.append(chip)
                
            except Exception as e:
                print(f"⚠️  Error processing chip: {e}")
                continue
                
    except Exception as e:
        print(f"❌ Error finding event chips: {e}")
        return []
    
    if not events:
        print("⚠️  No events found. Calendar might be empty.")
        return []
    
    return parse_events(events)


def parse_events(event_elements):
    """Parse event elements into structured data."""
    parsed_events = []
    today = datetime.now().date()
    
    for element in event_elements:
        # Try aria-label first, then inner text
        label = element.get_attribute("aria-label")
        if not label:
            try:
                inner_div = element.find_element(By.CLASS_NAME, "XuJrye")
                label = inner_div.text
            except:
                pass
        
        if not label:
            continue
        
        print(f"🔍 Parsing: {label}")
        
        # Try multiple patterns
        # Pattern 1: "1:30pm to 2:30pm, Block, Takumi Nishida, ..."
        match = re.match(r"(.+?)\s*(?:to|–|—|-)\s*(.+?),\s*(.+?)(?:,|$)", label, re.IGNORECASE)
        
        if match:
            start_str, end_str, title = match.groups()
        else:
            # Pattern 2: "Event Title, Monday, November 24⋅10:00 – 11:30am"
            match = re.match(r"(.+?),\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*.+?⋅(.+?)\s*[–—-]\s*(.+?)(?:,|$)", label, re.IGNORECASE)
            if match:
                title, start_str, end_str = match.groups()
            else:
                print(f"   ⚠️  Could not match pattern")
                continue
        
        try:
            start_time = parse_time_string(start_str.strip())
            end_time = parse_time_string(end_str.strip())
            
            # Try to extract date from the label (e.g., "November 26, 2025")
            event_date = today
            date_match = re.search(r"(\w+)\s+(\d+),\s+(\d{4})", label)
            if date_match:
                try:
                    month_name, day, year = date_match.groups()
                    event_date = datetime.strptime(f"{month_name} {day} {year}", "%B %d %Y").date()
                except:
                    pass
            
            # Create full datetime objects
            start_datetime = datetime.combine(event_date, start_time)
            end_datetime = datetime.combine(event_date, end_time)
            
            parsed_events.append({
                "title": title.strip(),
                "start": start_datetime,
                "end": end_datetime,
                "duration_minutes": int((end_datetime - start_datetime).total_seconds() / 60)
            })
            print(f"   ✅ Parsed: {title.strip()} at {start_time}")
        except ValueError as e:
            print(f"   ⚠️  Could not parse time: {e}")
            continue
    
    # Sort by start time
    parsed_events.sort(key=lambda x: x["start"])
    return parsed_events


def parse_time_string(time_str):
    """Parse time strings like '1pm', '2:30pm', '10am', '10:00am' into datetime.time."""
    time_str = time_str.lower().strip()
    
    # Remove spaces between time and am/pm
    time_str = re.sub(r'\s*(am|pm)', r'\1', time_str)
    
    # Try 12-hour format with minutes and am/pm (e.g., "2:30pm", "10:00am")
    try:
        return datetime.strptime(time_str, "%I:%M%p").time()
    except ValueError:
        pass
    
    # Try 12-hour format without minutes (e.g., "2pm")
    try:
        return datetime.strptime(time_str, "%I%p").time()
    except ValueError:
        pass
    
    # Try 24-hour format with minutes (e.g., "14:30")
    try:
        return datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        pass
    
    raise ValueError(f"Cannot parse time string: {time_str}")


def find_next_meeting(events):
    """Find the next upcoming meeting."""
    now = datetime.now()
    
    # Find upcoming events
    upcoming = [e for e in events if e["start"] > now]
    if upcoming:
        return upcoming[0]  # Already sorted by start time
    
    return None


def start_clock_app_timer(seconds, meeting_title=""):
    """Start a countdown timer in macOS Clock app using Shortcuts."""
    try:
        # Convert seconds to hours, minutes, seconds for display
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            time_str = f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            time_str = f"{minutes}m {secs}s"
        else:
            time_str = f"{secs}s"
        
        print(f"⏰ Starting Clock timer: {meeting_title}")
        print(f"   Duration: {time_str} ({seconds} seconds)")
        
        # Use macOS Shortcuts to start the timer
        # Pass seconds as stdin input
        result = subprocess.run(
            ["shortcuts", "run", "StartClockTimer"],
            input=str(seconds),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print(f"✅ Timer started in Clock app!")
            print(f"   Countdown: {time_str} until {meeting_title}")
            return True
        else:
            print(f"⚠️  Could not start timer via Shortcuts")
            print(f"   Return code: {result.returncode}")
            if result.stderr:
                print(f"   Error: {result.stderr}")
            if result.stdout:
                print(f"   Output: {result.stdout}")
            return False
        
    except subprocess.TimeoutExpired:
        print("❌ Timer command timed out (waited 30s)")
        print("   The shortcut may be waiting for permission - check Clock app")
        return False
    except Exception as e:
        print(f"❌ Failed to start timer: {e}")
        return False


def format_time_until(target_datetime):
    """Format time remaining until target datetime."""
    delta = target_datetime - datetime.now()
    
    if delta.total_seconds() < 0:
        return "Meeting already started"
    
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    seconds = int(delta.total_seconds() % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def get_todays_upcoming_meetings(events):
    """Get all meetings for today that haven't ended yet."""
    now = datetime.now()
    today = now.date()
    
    upcoming_today = [
        e for e in events 
        if e["end"] > now and e["start"].date() == today
    ]
    
    return sorted(upcoming_today, key=lambda x: x["start"])


def main():
    """Main execution flow - continuously queue meetings throughout the day."""
    print("🚀 Google Calendar Countdown Timer")
    print("=" * 50)
    print("📌 Continuous mode: Will queue timers for all meetings today")
    print("   Press Ctrl+C to stop\n")
    
    # Initialize Chrome driver
    driver = None
    try:
        driver = setup_chrome_driver()
        
        # Scrape events
        events = scrape_calendar_events(driver)
        
        # Close browser after getting events
        if driver:
            driver.quit()
            print("\n✅ Browser closed\n")
            driver = None
        
        if not events:
            print("📭 No events found in calendar")
            return
        
        # Display all events
        print(f"📋 Found {len(events)} events:")
        print("-" * 50)
        for i, event in enumerate(events, 1):
            print(f"{i}. {event['title']}")
            print(f"   {event['start'].strftime('%I:%M %p')} - {event['end'].strftime('%I:%M %p')} ({event['duration_minutes']} min)")
        print("-" * 50)
        
        # Continuous loop - queue meetings throughout the day
        while True:
            now = datetime.now()
            today = now.date()
            
            print(f"\n🔍 Checking for meetings on {today.strftime('%B %d, %Y')}...")
            print(f"   Current time: {now.strftime('%I:%M %p')}")
            
            # Get upcoming meetings for today
            todays_meetings = get_todays_upcoming_meetings(events)
            
            if not todays_meetings:
                print("\n🏁 No more meetings left today!")
                print("   Have a great rest of your day! 👋")
                break
            
            # Get the next meeting
            next_meeting = todays_meetings[0]
            time_until_start = (next_meeting["start"] - now).total_seconds()
            time_until_end = (next_meeting["end"] - now).total_seconds()
            
            # If meeting has already started, wait until it ends
            if time_until_start <= 0:
                print(f"\n📍 Meeting in progress: {next_meeting['title']}")
                print(f"   Ends at: {next_meeting['end'].strftime('%I:%M %p')}")
                print(f"   Time remaining: {format_time_until(next_meeting['end'])}")
                print(f"   Waiting for meeting to end...")
                
                # Sleep until meeting ends (check every 30 seconds)
                while datetime.now() < next_meeting["end"]:
                    time.sleep(30)
                
                print(f"✅ Meeting ended: {next_meeting['title']}")
                continue
            
            # Meeting is upcoming - start a timer
            print(f"\n⏭️  Next Meeting: {next_meeting['title']}")
            print(f"   Starts at: {next_meeting['start'].strftime('%I:%M %p')}")
            print(f"   Time until: {format_time_until(next_meeting['start'])}")
            
            # Calculate timer duration (full time until meeting starts)
            timer_seconds = int(time_until_start)
            
            if timer_seconds > 0 and timer_seconds < 86400:  # Less than 24 hours
                print(f"\n⏰ Starting timer for {timer_seconds // 60} minutes...")
                start_clock_app_timer(timer_seconds, next_meeting["title"])
                
                # Wait until the meeting starts
                print(f"⏳ Waiting for meeting to start...")
                while datetime.now() < next_meeting["start"]:
                    time.sleep(30)
                
                print(f"\n🎯 Meeting started: {next_meeting['title']}")
                
                # Now wait until it ends
                print(f"⏳ Waiting for meeting to end...")
                while datetime.now() < next_meeting["end"]:
                    time.sleep(30)
                
                print(f"✅ Meeting ended: {next_meeting['title']}")
            else:
                print(f"\n⚠️  Meeting is too far away or invalid time - skipping")
                break
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()
            print("\n✅ Browser closed")


if __name__ == "__main__":
    main()

