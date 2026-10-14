from OpenSSL import crypto

# Generate key
key = crypto.PKey()
key.generate_key(crypto.TYPE_RSA, 2048)

# Generate certificate
cert = crypto.X509()
cert.get_subject().C = "IN"
cert.get_subject().O = "SkillMentor"
cert.get_subject().CN = "localhost"
cert.set_serial_number(1000)
cert.gmtime_adj_notBefore(0)
cert.gmtime_adj_notAfter(365*24*60*60)  # Valid for 1 year
cert.set_issuer(cert.get_subject())
cert.set_pubkey(key)
cert.sign(key, 'sha256')

# Save certificate
with open("cert.pem", "wb") as f:
    f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

# Save private key
with open("key.pem", "wb") as f:
    f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))

print("✓ cert.pem and key.pem generated successfully!")
