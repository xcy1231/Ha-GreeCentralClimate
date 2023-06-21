import base64
import json
import logging
from Crypto.Cipher import AES

REQUIREMENTS = ['pycryptodome']

_LOGGER = logging.getLogger(__name__)

CIPER_KEY = "a3K8Bx%2r8Y7#xDh"


def Pad(s):
    aesBlockSize = 16
    return s + (aesBlockSize - len(s) % aesBlockSize) * chr(aesBlockSize - len(s) % aesBlockSize)


def ciperEncrypt(data, key=CIPER_KEY):
    # _LOGGER.info('Crypto encrypt key: {}'.format(key))
    cipher = AES.new(key.encode("utf8"), AES.MODE_ECB)
    jsonStr = json.dumps(data).replace(' ', '')
    padStr = Pad(jsonStr)
    encryptStr = cipher.encrypt(padStr.encode("utf-8"))
    finalStr = base64.b64encode(encryptStr).decode('utf-8')
    # _LOGGER.info('Crypto encrypt str: {}'.format(finalStr))
    return finalStr


def ciperDecrypt(data, key=CIPER_KEY):
    # _LOGGER.info('Crypto decrypt key: {}'.format(key))
    decodeData = base64.b64decode(data)
    cipher = AES.new(key.encode("utf8"), AES.MODE_ECB)
    decryptData = cipher.decrypt(decodeData).decode("utf-8")
    replacedData = decryptData.replace('\x0f', '').replace(
        decryptData[decryptData.rindex('}')+1:], '')
    return replacedData
