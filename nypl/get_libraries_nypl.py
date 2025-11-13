from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pandas as pd
import time
import requests
import json

def get_json_response():
  url = "https://scout.nypl.org/api/graphql"

  headers = {
      "content-type": "application/json",
      "accept": "*/*",
      "origin": "https://www.nypl.org",
      "referer": "https://www.nypl.org/",
      "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"
  }

  payload = {
      "operationName": "LocationsQuery",
      "query": """
      query LocationsQuery {
        refineryAllLocations {
          locations {
            id
            name
            address_line1
            address_line2
            locality
            administrative_area
            postal_code
            __typename
          }
          __typename
        }
      }
      """,
      "variables": {}
  }

  response = requests.post(url, json=payload, headers=headers)

  print("Status code:", response.status_code)
  if response.status_code == 200:
      df = pd.DataFrame(response.json()["data"]["refineryAllLocations"]["locations"])
      df["name"] = df["name"].astype(str) + " " + df["postal_code"].astype(str)
      return df
  else:
      print("Error response:", response.text)

def get_from_html(headless=False):

    options = Options()
    if headless:
        options.add_argument("--headless=new")  # Use new headless mode in Edge
    driver = webdriver.Edge(options=options)
    driver.get("https://nypl.org/locations")
    wait = WebDriverWait(driver, 10)
    ul_element = wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//ul[@style='list-style-type:none;padding:0']")
        )
    )
    html_outer = ul_element.get_attribute("outerHTML")
    driver.quit()

    soup = BeautifulSoup(html_outer, "html.parser")
    library_items = soup.find_all('li')

    data = []

    for item in library_items:
        library = {}
        
        # Extract library name and URL
        h2 = item.find('h2', class_='chakra-heading')
        a_tag = h2.find('a') if h2 else None
        library['Name'] = a_tag.text.strip() if a_tag else None
        library['URL'] = a_tag['href'] if a_tag else None
        
        # Extract address
        address_div = item.find('div', class_='address')
        library['Address'] = address_div.text.strip() if address_div else None
        library['Zip'] = address_div.text.strip().split()[-1] if address_div else None
        
        # Extract phone number
        phone_div = item.find('div', class_='phone')
        library['Phone'] = phone_div.text.strip() if phone_div else None
        
        # Extract accessibility info (text inside the div following the icon)
        accessible_div = item.find_all('div', class_='chakra-stack')
        accessibility_info = None
        for div in accessible_div:
            if div.find('svg', role='img'):  # find div containing an svg icon
                # The text is usually in the sibling div or within this div but after the icon
                texts = div.find_all('div', class_='css-0')
                if texts:
                    accessibility_info = texts[-1].text.strip()
                    break
        library['Accessibility'] = accessibility_info
        
        # Extract today's hours
        hours_div = None
        for div in accessible_div:
            if div.find('svg', title='clock icon'):
                hours_div = div
                break
        if hours_div:
            hours_text_div = hours_div.find('div', class_='css-1xsa88d')
            library['Todays Hours'] = hours_text_div.text.strip() if hours_text_div else None
        else:
            library['Todays Hours'] = None
        
        # Extract map directions link
        map_link = None
        buttons_divs = item.find_all('div', class_='chakra-stack')
        for div in buttons_divs:
            a = div.find('a', string='Get Directions')
            if a:
                map_link = a['href']
                break
        library['Map Link'] = map_link
        
        data.append(library)
    df = pd.DataFrame(data)
    df["Name"] = df["Name"].astype(str) + " " + df["Zip"].astype(str)
    return df

def store_libraries_nypl(path, headless=True):
    json_df = get_json_response()
    print("POST request complete.")
    html_df = get_from_html(headless=headless)
    print("HTML parsing complete.")
    df = json_df.merge(html_df, left_on="name", right_on="Name", validate="one_to_one")
    df.to_json(path, orient="records", indent=4)

if __name__ == "__main__":
    store_libraries_nypl("data/nypl_all.json", headless=False)
