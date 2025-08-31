from heyoo import WhatsApp
from core.settings import HEYOO_TOKEN, HEYOO_PHONE_ID, OWNER_PHONE_NUMBER

def main():
    messenger = WhatsApp(HEYOO_TOKEN, phone_number_id=HEYOO_PHONE_ID)
    print("Token:", HEYOO_TOKEN[:3], ".....")
    print("Phone ID:", HEYOO_PHONE_ID)
    print("Destino:", OWNER_PHONE_NUMBER)

    response = messenger.send_template(
        template="hello_world",
        recipient_id=OWNER_PHONE_NUMBER,
        lang="en_US",
        components=[]
    )
    print("Response:", response)

if __name__ == "__main__":
    main()
