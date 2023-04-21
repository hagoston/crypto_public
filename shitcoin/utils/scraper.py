from bs4 import BeautifulSoup
from icecream import ic
import socket
import requests
import requests.packages.urllib3.util.connection as urllib3_cn
import cloudscraper

ic.configureOutput(includeContext=True)
ic.disable()

# download page
class Scraper():
    def __init__(self):
        # module to bypass Cloudflare's anti-bot page
        self.scraper = cloudscraper.create_scraper()

        # force ipv4
        if 0:
            urllib3_cn.allowed_gai_family = self.allowed_gai_family

    def allowed_gai_family(self):
        family = socket.AF_INET     # force ipv4
        return family
        
    def get_page(self, url):
        webpage = self.scraper.get(url)

        # webpage = requests.get(url, 
        #                        headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(webpage.content, 'html5lib')
        return soup
    
    def get(self, url):
        return self.scraper.get(url)
    
    def bs(self, content):
        return BeautifulSoup(content, 'lxml')