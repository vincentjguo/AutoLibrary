import datetime
import json
import os
import pickle
import sys
import time
from datetime import date

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver import DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

dp_url = "https://libcal.uwaterloo.ca/reserve/spaces/dplibrary"
dc_url = "https://libcal.uwaterloo.ca/reserve/spaces/dclibrary"

CREDENTIALS = None
DUO_CODES = None
COOKIE_JAR = "./cookie.txt"

target_time = datetime.time(4, 30)

# Allowed time variation (increments of 15min)
EPSILON = 30
MIN_DURATION = 120

# Initialize driver
capabilities = DesiredCapabilities.EDGE
capabilities['ms:inPrivate'] = True
driver = webdriver.Edge(capabilities=capabilities)


def get_url(url):
    driver.get(url)
    time.sleep(3)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
    load_cookie()


def add_time(t, delta):
    return (datetime.datetime.combine(datetime.date(1, 1, 1), t) + delta).time()


def days_forward(target):
    if target < date.today():
        raise Exception("Target date is in the past")
    return (target - date.today()).days


def get_day(num_days):
    for x in range(num_days):
        driver.find_element(By.CLASS_NAME, "fc-next-button").click()


def find_valid_time(target):
    for delta in range(0, EPSILON, 15):
        possible_time = add_time(target, datetime.timedelta(minutes=delta))
        # Assume PM because we are not psychos
        try:
            list_of_times = WebDriverWait(driver, timeout=3).until(
                lambda d: d.find_elements(By.XPATH,
                                          f"//*[contains(@title, '{possible_time.hour}:{possible_time.minute:02d}pm') and not(contains(@title, 'Unavailable'))]"))
        except TimeoutException:
            continue
        print("Possible List of Times:")
        [print(i.get_attribute("title")) for i in list_of_times]
        for t in list_of_times:
            title = t.get_attribute("title")
            # Slow implementation
            valid_time_slot = True
            if "Available" in title:
                for time_slot in (add_time(possible_time, datetime.timedelta(minutes=n)) for n in
                                  range(15, MIN_DURATION, 15)):
                    new_title = title.replace(f"{possible_time.hour}:{possible_time.minute:02d}pm",
                                              f"{time_slot.hour}:{time_slot.minute:02d}pm")
                    try:
                        driver.find_element(By.XPATH, f'//*[@title="{new_title}"]')
                    except NoSuchElementException:
                        valid_time_slot = False
                        break
            if valid_time_slot:
                return title
    return None


def get_time(target):
    element_title = find_valid_time(target)
    if element_title is None:
        return None
    print("Found: " + element_title)
    time.sleep(3)
    driver.find_element(By.XPATH, f'//*[@title="{element_title}"]').click()
    return True


def submit_time():
    time.sleep(3)
    driver.find_element(By.XPATH, "//*[@id='submit_times']").click()
    try:
        sign_in()
        time.sleep(3)
    except TimeoutException:
        print("Skipped Sign In")
    driver.find_element(By.ID, 'terms_accept').click()
    time.sleep(3)
    driver.find_element(By.XPATH, "//*[@type='checkbox']").click()
    driver.find_element(By.ID, 's-lc-eq-bform-submit').click()


def save_cookie():
    with open(COOKIE_JAR, 'wb') as filehandler:
        pickle.dump(driver.get_cookies(), filehandler)


def load_cookie():
    if os.stat(COOKIE_JAR).st_size == 0:
        return
    with open(COOKIE_JAR, 'rb') as cookiesfile:
        cookies = pickle.load(cookiesfile)
        for cookie in cookies:
            driver.add_cookie(cookie)


def sign_in():
    username = WebDriverWait(driver, timeout=10).until(lambda d: d.find_element(By.ID, 'userNameInput'))
    username.send_keys(CREDENTIALS[0])
    driver.find_element(By.ID, 'nextButton').click()
    password = WebDriverWait(driver, timeout=10).until(lambda d: d.find_element(By.ID, 'passwordInput'))
    password.send_keys(CREDENTIALS[1])
    driver.find_element(By.ID, 'submitButton').click()
    # check for duo auth
    try:
        WebDriverWait(driver, timeout=10).until(lambda d: d.find_elements(By.ID, 'duo_iframe'))
        time.sleep(30)  # timeout login request
        # if authenticated
        if len(driver.find_elements(By.ID, 'duo_iframe')) == 0:
            return
        driver.find_element(By.ID, "passcode").click()
        time.sleep(2)
        if len(DUO_CODES) == 0:
            raise Exception("All Duo codes have been used")
        driver.find_element(By.CLASS_NAME, "passcode-input").send_keys(DUO_CODES.pop(0))  # send code
        driver.find_element(By.XPATH, "//*[@type='checkbox']").click()  # click on remember me
        driver.find_element(By.ID, 'passcode').click()
    except TimeoutException:
        print("DUO Auth Bypassed")

    # saves all cookies
    save_cookie()


def book_date(target_day):
    get_url(dc_url)

    get_day(days_forward(target_day))

    if get_time(target_time) is None:
        get_url(dp_url)
        assert driver is not None

        get_day(days_forward(target_day))
        if get_time(target_time) is None:
            print("No valid time found")
            driver.close()
            sys.exit(1)

    submit_time()


if __name__ == "__main__":
    # get credentials
    cred = json.load(open('credentials.json'))
    CREDENTIALS = {cred["Username"], cred["Password"]}
    DUO_CODES = cred["AuthCodes"]
    target_day = datetime.date(2022, 10, 27)  # date.today() + datetime.timedelta(7)
    book_date(target_day)
    print("Booked Successfully for " + target_day.isoformat())


