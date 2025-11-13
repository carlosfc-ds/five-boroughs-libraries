from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import pandas as pd
import requests
import json
from tqdm import tqdm
from bs4 import BeautifulSoup

class NYPL:
    def __init__(self, response_path, dataframe_path):
        self.root_url = 'https://www.nypl.org/'
        self.response_path = response_path
        self.dataframe_path = dataframe_path

    def store_response(self):
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

        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                self.response = response.json()
            else:
                print("Request failed with status code:", response.status_code)
        except requests.exceptions.RequestException as e:
            print("An error occurred:", e)
        
        with open(self.response_path, 'w') as f:
            json.dump(self.response, f, indent=4)

    def selenium_scrape_unordered_list(self, headless):
        options = Options()
        if headless:
            options.add_argument('--headless')
        driver = webdriver.Edge(options=options)
        wait = WebDriverWait(driver, 10)

        driver.get("https://nypl.org/locations")
        ul_element = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//ul[@style='list-style-type:none;padding:0']")
            )
        )
        self.unordered_list = ul_element.get_attribute("outerHTML")
        driver.quit()

    def process_unordered_list(self):
        soup = BeautifulSoup(self.unordered_list, "html.parser")
        libraries = []
        for item in soup.find_all('li'):
            library = {}
            
            h2 = item.find('h2', class_='chakra-heading')
            a_tag = h2.find('a') if h2 else None
            library['name'] = a_tag.text.strip() if a_tag else None
            library['url'] = a_tag['href'] if a_tag else None
            
            address_div = item.find('div', class_='address')
            library['address'] = address_div.text.strip() if address_div else None
            library['zip'] = address_div.text.strip().split()[-1] if address_div else None
            
            phone_div = item.find('div', class_='phone')
            library['phone'] = phone_div.text.strip() if phone_div else None
            
            accessible_div = item.find_all('div', class_='chakra-stack')
            accessibility_info = None
            for div in accessible_div:
                if div.find('svg', role='img'):
                    texts = div.find_all('div', class_='css-0')
                    if texts:
                        accessibility_info = texts[-1].text.strip()
                        break
            library['accesibility'] = accessibility_info
            
            map_link = None
            buttons_divs = item.find_all('div', class_='chakra-stack')
            for div in buttons_divs:
                a = div.find('a', string='Get Directions')
                if a:
                    map_link = a['href']
                    break
            library['map link'] = map_link
            libraries.append(library)

        self.libraries = pd.DataFrame(libraries)
        self.libraries["name"] = self.libraries["name"].astype(str) + " " + self.libraries["zip"].astype(str)

    def merge_libraries_and_response(self):
        with open(self.response_path, 'r') as f:
            response = json.load(f)
        response_df = pd.DataFrame(response["data"]["refineryAllLocations"]["locations"])
        response_df["name"] = response_df["name"].astype(str) + " " + response_df["postal_code"].astype(str)
        self.libraries = response_df.merge(self.libraries, left_on="name", right_on="name", validate="one_to_one")

    def selenium_scrape_active_hours(self, headless):
        options = Options()
        if headless:
            options.add_argument("--headless")
        driver = webdriver.Edge(options=options)
        wait = WebDriverWait(driver, 10)

        unable_to_scrape = []
        self.library_hours = {}

        for id, url in tqdm(self.libraries[['id', 'url']].values.tolist(), desc='Scraping library pages'):
            driver.get(url)
            try: 
                condition = EC.any_of(
                    EC.visibility_of_element_located((By.XPATH, "//h2[text()='Regular Hours']")),
                    EC.visibility_of_element_located((By.XPATH, "//p[@data-testid='ds-text' and contains(text(), 'Temporarily Closed')]")),
                    EC.visibility_of_element_located((By.XPATH, "//button[@id='tabs--r59kd5t6---tab-1' and normalize-space(text())='Upcoming Hours']"))
                )
                header_element = wait.until(condition)

                if header_element.text.strip() == 'Regular Hours':
                    parent_div = header_element.find_element(By.XPATH, "./following-sibling::table[1]")
                    rows = parent_div.find_elements(By.TAG_NAME, 'tr')

                    hours_data = {}
                    for row in rows[1:]:
                        cols = row.find_elements(By.TAG_NAME, 'th') + row.find_elements(By.TAG_NAME, 'td')
                        day = cols[0].text if len(cols) > 0 else ''
                        hours = cols[1].text if len(cols) > 1 else ''
                        hours_data[day] = hours
                    self.library_hours[id] = hours_data
                
                elif header_element.text.strip() == 'Temporarily Closed':
                    self.library_hours[id] = {'Monday': 'Temporarily Closed', 'Tuesday': 'Temporarily Closed', 'Wednesday': 'Temporarily Closed',
                                        'Thursday': 'Temporarily Closed', 'Friday': 'Temporarily Closed', 'Saturday': 'Temporarily Closed',
                                        'Sunday': 'Temporarily Closed'}
                
                elif header_element.text.strip() == 'Upcoming Hours':
                    upcoming_tab_panel = wait.until(
                        EC.visibility_of_element_located((By.ID, "tabs--r59kd5t6---tabpanel-1"))
                    )
                    table = upcoming_tab_panel.find_element(By.CSS_SELECTOR, "table.css-fvtdov")
                    rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
                    schedule_data = {}
                    for row in rows:
                        day = row.find_element(By.CSS_SELECTOR, "th p[data-testid='ds-text']").text.strip()
                        date = row.find_element(By.CSS_SELECTOR, "td:nth-of-type(1) p[data-testid='ds-text']").text.strip()
                        hours = row.find_element(By.CSS_SELECTOR, "td:nth-of-type(2) p[data-testid='ds-text']").text.strip()
                        schedule_data[day] = hours
                    self.library_hours[id] = schedule_data

            except Exception:
                unable_to_scrape.append(url)

        driver.quit()
    
    def process_active_hours(self):
        self.df = self.libraries
        for id, hours in self.library_hours.items():
            for day_of_week in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
                self.df.loc[self.df['id'] == id, day_of_week] = hours[day_of_week]
    
    def store_dataframe(self):
        self.df.to_json(self.dataframe_path, orient='records', indent=4)
    
    def load_data(self):
        self.df = pd.read_json(self.dataframe_path, orient='records')

    def get_df(self):
        return self.df
