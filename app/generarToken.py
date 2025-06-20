import bcrypt

password = "123".encode("utf-8")
hashed_password = bcrypt.hashpw(password, bcrypt.gensalt())
print(hashed_password)