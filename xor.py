#
# NB : this is not secure
# from http://code.activestate.com/recipes/266586-simple-xor-keyword-encryption/
# added base64 encoding for simple querystring :)
#
# RK: Retrieved from https://gist.github.com/revolunet/2412240
# Thank you to Julien Bouquillon, https://gist.github.com/revolunet
 
def xor_crypt_string(data, key='aM982&*3emTH(', encode=False, decode=False):
	from itertools import izip, cycle
	import base64
	if decode:
		data = base64.decodestring(data)
	xored = ''.join(chr(ord(x) ^ ord(y)) for (x,y) in izip(data, cycle(key)))
	if encode:
		return base64.encodestring(xored).strip()
	return xored
 
if __name__== "__main__":
	secret_data = "mypassword"
	print xor_crypt_string(secret_data, encode=True)
	print xor_crypt_string(xor_crypt_string(secret_data, encode=True), decode=True)