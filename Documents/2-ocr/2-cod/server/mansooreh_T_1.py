from PIL import Image, ImageEnhance, ImageFilter
import cv2
import numpy as np
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from elasticsearch import Elasticsearch
from urllib.parse import urlparse
from wand.image import Image as wi
from os import listdir
import io, os
import config
import base64
import requests
import shutil
from tesserocr import PyTessBaseAPI
from lxml import etree
from difflib import SequenceMatcher
import hocrTOpdf_3_2
from socketserver import ThreadingMixIn
import datetime
from wand.color import Color
import requests
#import paho.mqtt.client as mqttClient
import time


es = Elasticsearch([{'host': config.HOST, 'port': config.PORT}])


class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    pass


def read_pdf(address):
    print('________________START in read_pdf method __________________ \n')
    pdfFile = wi(filename=address, resolution=300)
    image = pdfFile.convert('jpeg')
    imageBlobs = []

    # this line add in v2.4
    for img in image.sequence:
        imgPage = wi(image=img)
        imgPage.background_color = Color("white")
        imgPage.alpha_channel = 'remove'
        images = io.BytesIO(imgPage.make_blob('jpg'))
        imageBlobs.append(images)

    print(len(imageBlobs))
    return imageBlobs

def read_dir(address):
    print('________________START in read_dir method __________________ \n')
    imageBlobs = []
    if os.path.isdir(address):
        for idx, file in enumerate(sorted(os.listdir(address))):
            print("FILE IN ADDRESS: ",file)
            imageBlobs.append(address + file)

    else:
        print("ERROR:the path is not directory, please select a directory")
        

    return imageBlobs


def image_processing(image_pil):
    print('________________START in image processing method ________________ \n')
    im2 = image_pil.filter(ImageFilter.MedianFilter())
    enhancer = ImageEnhance.Contrast(im2)
    im2 = enhancer.enhance(3)
    im2.save('median_image.jpg')
    # imgarry = np.array(im.convert("L"))
    imgarry = cv2.imread('median_image.jpg', 0)
    imgarryBlur = cv2.medianBlur(imgarry, 5)
    ret, im_otsu = cv2.threshold(imgarryBlur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cv2.imwrite('otsu_image.jpg', im_otsu)
    imPIL = Image.open('otsu_image.jpg')

    return imPIL


class MyHandler(BaseHTTPRequestHandler):

    def _set_headers(self):
        print('________________ START in _set_headers method ________________ \n')
        self.send_response(200)
        self.send_header('Content-type', 'x'
                                         ''
                                         ''
                                         '')
        self.end_headers()

    def do_OCR(self):
        print('>>>>>>>>>>>>>>>>>>>> in do_OCR method <<<<<<<<<<<<<<<<<<<< \n')
        self._set_headers()
        print('________________ Exit _set_headers method ___________________ \n')
        self.data_string = self.rfile.read(int(self.headers['Content-Length']))
        #self.send_response(200)
        self.end_headers()
        recv_data = json.loads(self.data_string.decode('UTF-8').strip())
        print("data receve by this format \n")
        print("{}".format(recv_data))
        file_name = recv_data['file_name']
        doc_type = 'student'
        language = recv_data['language']
        image_checkbox = int(recv_data["image_checkbox"])
        address = recv_data['address']
        #doc_type = recv_data['doc_type']
        #toobatelId=recv_data['toobatelId']
        if  (file_name or  language  or image_checkbox): 
            file_name = recv_data['file_name'].replace(" ", "_")
            #address = "/opt/lampp/htdocs/toosApi/uploads/"+file_name

        else:
            self.wfile.write(json.dumps({"message":"ERROR too101: please fill in all fields"}).encode())
    

        #### json key value will be inserted and then saved in the elasticsearch url
        doc = {
            'file_name': file_name,
            'language': language,
            'total_page': 0,
            'image1': "",
            'image2': "",
            'content': "",

        }

        epoch = str(datetime.datetime.now()).split()
        date = epoch[0].split('-')
        timee = epoch[1].split(':')
        doc_id = ''.join(date) + ''.join(timee)
        #print('doc_id:', doc_id)

        ########  read input file and convert it to one or multiple images in a list 
        imageBlobs_list = []
        imageBlobs_pdf = []
        if address.endswith('.pdf'):
            imageBlobs_pdf = read_pdf(address)
            print('________________ Exit read_pdf ________________')
            #print(len(imageBlobs_pdf))
            doc['total_page'] = len(imageBlobs_pdf)
        elif address.endswith('.jpg') or address.endswith('.JPG') or address.endswith('.jpeg') or file_name.endswith(
                '.png') or file_name.endswith('.tiff') or file_name.endswith('.tif') or address.endswith(
            '.PNG') or address.endswith('.JPEG'):

            print('in do_OCR method read image ...')
            imageBlobs_list.append(address)
            # if file_name.endswith('.png')or address.endswith('.PNG') or address.endswith('.JPEG'):
            #     im = Image.open(address)
            #     rgb_im = im.convert('RGB')


            doc['total_page'] = 1
        else:

            imageBlobs_list = read_dir(address)
            if not imageBlobs_list:
                self.wfile.write(json.dumps({"message":"ERROR too103: file is not available in the  Address server"}).encode())

            print('________________ Exit read_dir ________________')
            doc['total_page'] = len(imageBlobs_list)
            print("TOTAL PAGE: ",len(imageBlobs_list))
            print("\n")
        # ####### encode base64 the sequence of images and insert it to elasticsearch #######
        page_num = 0
        if imageBlobs_pdf:
            imageBlobs_list = imageBlobs_pdf
       
        for imgB in imageBlobs_list:
            if not imageBlobs_pdf:
                with open(imgB, "rb") as imageFile:
                    encoded_string = base64.b64encode(imageFile.read()).decode('utf-8')

            elif imageBlobs_pdf:
                encoded_string = base64.b64encode(imgB.read()).decode('utf-8')
                print('pdf is encoded')
                print('page:', page_num)
                if page_num == 0:
                    print('page_num:', page_num, 'imgb:', imgB)
                    first_encode = encoded_string

            doc['image1'] = str(encoded_string)

            #### change resolution of image to low resolution
            image_pil = Image.open(imgB)
            wanted_dpi = 10.0
            try:
                dpi_x, dpi_y = image_pil.info["dpi"]
            except KeyError:
                dpi_x, dpi_y = (wanted_dpi, wanted_dpi)

            print("change DPI to :",dpi_x, dpi_y)
            x=round(image_pil.width * wanted_dpi / dpi_x)
            y=round(image_pil.height * wanted_dpi / dpi_y)
           
            image_pil.resize(
                (round(image_pil.width * wanted_dpi / dpi_x), round(image_pil.height * wanted_dpi / dpi_y)),
                resample=Image.LANCZOS)

            new_width = int(image_pil.size[0] * 0.5)
            new_height = int(image_pil.size[1] * 0.5)
            image_pil = image_pil.resize((new_width, new_height), Image.ANTIALIAS)

            buffered = io.BytesIO()
            image_pil.save(buffered, format="JPEG")
            encoded_low_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

            # save low resolution image in doc to save in elasticserach
            doc['image2'] = str(encoded_low_image)
            page_num = page_num + 1
            print(page_num)
            res_index = es.index(index='library1', doc_type=doc_type, id=doc_id + '_' + str(page_num), body=doc)
            es.indices.refresh(index='library1')


       
        print("in get method")
        # doc_id = recv_data['doc_id']
        image_checkbox = int(recv_data["image_checkbox"])

        url = 'http://' + config.HOST + ':' + str(config.PORT) + '/library1/' + doc_type + '/' + doc_id + '_'
        rr = requests.get(url + str(1) + '/').json()
        total = rr['_source']['total_page']
        total_list = []

        for i in range(total):
            print('page number:' , i)
            r = requests.get(url + str(i + 1) + '/').json()

            doc = {
                'file_name': r['_source']['file_name'],
                'language': r['_source']['language'],
                'total_page': r['_source']['total_page'],
                'image1': r['_source']["image1"],
                'image2': r['_source']["image2"],
                'content': r['_source']["content"],
               
            }

            # if ghablan ocr nashodeh bud, then ocr kon
            if not doc['content']:
                jpg_bytes = base64.b64decode(r['_source']['image1'])
                image_pil = Image.open(io.BytesIO(jpg_bytes))
                image = np.array(image_pil)

                if image_checkbox == 1:
                    enhanced_image = image_processing(image_pil)
                else:
                    enhanced_image = image_pil

                ##### do OCR with tesseract for different languages
                ##### create text and data by using pytesseract image_to_string and image_to_data. both of these function give information.
                ##### we use text extension to save image as a text and hocr extension for rank and highlight words
                if language == 'fas':

                    with PyTessBaseAPI(lang='test_fas116_justify') as api:
                        print('OCR', i)
                        api.SetImage(enhanced_image)
                        h_data = api.GetHOCRText(0)

                elif language == 'eng':

                    with PyTessBaseAPI(lang='eng') as api:
                        api.SetImage(enhanced_image)
                        h_data = api.GetHOCRText(0)

                elif language == 'ara':

                    with PyTessBaseAPI(lang='ara') as api:
                        api.SetImage(enhanced_image)
                        h_data = api.GetHOCRText(0)

                elif language == 'fas+eng':
                    with PyTessBaseAPI(lang='test_fas116_justify+eng') as api:
                        api.SetImage(enhanced_image)
                        h_data = api.GetHOCRText(0)
                
                elif language == 'fas+ara':
                    with PyTessBaseAPI(lang='test_fas116_justify+ara') as api:
                        api.SetImage(enhanced_image)
                        h_data = api.GetHOCRText(0)  
                else: 
                    with PyTessBaseAPI(lang='test_fas116_justify') as api:
                        api.SetImage(enhanced_image)
                        h_data = api.GetHOCRText(0)  
                        

                doc['content'] = h_data

                res_index = es.index(index='library1', doc_type=doc_type, id=doc_id + '_' + str(i), body=doc)

                tree = etree.fromstring(h_data)
                text_data = etree.tostring(tree, encoding='UTF-8', method="text").decode("utf-8")
            # dar gheir in sorat agar ghablan ocr shodeh hala tabdil be pdf kon
            else:
                hocr = doc['content']
                tree = etree.fromstring(hocr)
                text_data = etree.tostring(tree, encoding='UTF-8', method="text").decode("utf-8")

            total_list.append(text_data)

        total_text = '\n'.join(total_list)
        #print(total_text)
        FILEPATH = '/tmp/' + file_name + '.txt'
        print('FILEPATH :' + FILEPATH+ "\n")

        with open(FILEPATH, 'w') as wfile:
            wfile.write(total_text)

        # r = requests('total_text')

        #url = 'http://api.toobatech.ir/ToobatelUploadFile?'
        #mansooreh 
        #please change url to this 
        #url = 'http://192.168.96.235:443/api/upload/hash/file'
        #endmansooreh

        #data = {
        #"password":"ocrfile@123" ,
        #"username":"toobatelocrfile",
        #}
        files = {'file':( open(FILEPATH))}
        print(files)
        #response_toos = requests.post(url, data=data,files=files)
        #hashname=response_toos.json()['hashNameFile'].split(' ')[0].replace("'","")
        #print(hashname,type(hashname))


        #hashname=str(toos_respons['hashNameFile'])
        with open(FILEPATH, 'rb') as f:
            self.send_response(200)
            self.send_header("Content-Type", 'application/octet-stream')
            ##show in client this:Content-Disposition: attachment; filename="b'afat-e-towhid.jpg.txt'"

            self.send_header("Content-Disposition",
                             'attachment; filename="{}"'.format(os.path.basename(FILEPATH.encode('utf-8'))))
            fs = os.fstat(f.fileno())
            self.send_header("Content-Length", str(fs.st_size))
            self.end_headers()
            shutil.copyfileobj(f, self.wfile)
        response = {
            #'hashNameFile': hashname,
            #'file_name': file_name,
            #'language': language,
            #"toobatelId": toobatelId

                  
        }
        #_______________send RESPONSE ___________
        self.send_response(200)
        #self.wfile.write(json.dumps(response).encode('utf-8'))

        def on_message(client, userdata, message):
            print("message received ", str(message.payload.decode("utf-8")))


        #_______________push_Broker ___________
        #broker_address = "217.218.171.92"
        #client = mqttClient.Client("P1")  # create new instance
        #client.on_message = on_message  # attach function to callback
        #client.connect(broker_address)  # connect to broker
        #client.loop_start()  # start the loop
        # client.subscribe("OCR/ResultFile")
        #print("Publishing message to topic", "OCR/ResultFile")
        #client.publish("OCR/ResultFile", str(response))
        
        #time.sleep(4)  # wait
        #client.loop_stop()  # stop the loop







        return
       

    def do_HEAD(self):
        self._set_headers()
    def do_POST(self):
        self._set_headers()


def run(server_class=HTTPServer, handler_class=MyHandler, port=config.server_Port):
    server_address = (config.server_Host, port)
    # httpd = server_class(server_address, handler_class)
    httpd = ThreadingSimpleServer(server_address, handler_class)
    print('Starting server listen...')

    httpd.serve_forever()


if __name__ == "__main__":
    from sys import argv

if len(argv) == 2:
    run(port=int(argv[1]))
else:
    run()
