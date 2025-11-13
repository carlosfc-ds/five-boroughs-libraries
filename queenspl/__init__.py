import pandas as pd
import requests
import json
from bs4 import BeautifulSoup

class QueensPL:
    def __init__(self, response_path, dataframe_path):
        self.root_url = 'https://www.queenslibrary.org/'
        self.response_path = response_path
        self.dataframe_path = dataframe_path
    
    def store_response(self):
        url = "https://www.queenslibrary.org/about-us/locations-ajax"

        try:
            response = requests.get(url)
            if response.status_code == 200:
                self.response = response.json()
            else:
                print("Request failed with status code:", response.status_code)
        except requests.exceptions.RequestException as e:
            print("An error occurred:", e)
        
        with open(self.response_path, 'w') as f:
            json.dump(self.response, f, indent=4)


    def process_response(self):
        with open(self.response_path, 'r') as f:
            self.response = json.load(f)

        rows = []
        for location in self.response['locationCards']:
            if location['branch_name'] == 'aaQPLAnywhere':
                continue

            row = {}
            row['branch_name'] = location['branch_name']
            card_html = location['card']

            soup = BeautifulSoup(card_html, 'html.parser')

            address_div = soup.find('div', class_='address')
            address = ' '.join(address_div.stripped_strings) if address_div else None
            row['address'] = address

            phone = soup.find('div', class_='phone').get_text(strip=True) if soup.find('div', class_='phone') else None
            row['phone'] = phone

            img_tag = soup.find('img')
            image_url = img_tag['src'] if img_tag else None
            row['image_url'] = self.root_url + image_url

            cta_link = soup.find('div', class_='call-to-action').find('a')['href']
            row['link'] = self.root_url + cta_link

            office_hours_items = soup.find_all('div', class_='office-hours__item')

            for item in office_hours_items:
                day = item.find('span', class_='office-hours__item-label').get_text(strip=True).replace(':', '')
                time_slots = item.find_all('span', class_='office-hours__item-slots')
                hours = " - ".join([slot.get_text(strip=True) for slot in time_slots])

                row[day] = hours
            rows.append(row)

        self.df = pd.DataFrame(rows)
    
    def store_dataframe(self):
        self.df.to_json(self.dataframe_path, orient='records', indent=4)
    
    def load_data(self):
        self.df = pd.read_json(self.dataframe_path, orient='records')

    def get_df(self):
        return self.df
