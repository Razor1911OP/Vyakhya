"""
Synthetic message templates for Vyakhya (SYNTHETIC DATA ONLY).

Structure: TEMPLATES[key][lang] -> list of template strings with {slot} placeholders.
  key  = scam family (label 1) or benign subtype (label 0)
  lang = "en" (English), "hi-en" (romanised Hinglish), "hi" (Devanagari Hindi)

Each template gets a stable ID: <key>_<lang>_<NN>. Splits for evaluation are done
by template / family, never by random row, so a template's paraphrases never leak
between train and test.

Benign subtypes deliberately include HARD NEGATIVES (genuine bank KYC reminders,
genuine refunds, real courier updates, family money requests, real job offers)
so the text model cannot win by keyword-spotting "KYC", "refund", "parcel", "OTP".
Names, numbers, links and VPAs are fictional placeholders.
"""

SCAM_FAMILIES = ["kyc_refund", "digital_arrest", "lottery", "upi_collect", "job_task"]
BENIGN_SUBTYPES = [
    "otp_notice", "delivery", "family_chat", "bank_genuine",
    "merchant_bill", "refund_genuine", "job_genuine",
]

TEMPLATES = {
    # ------------------------------------------------------------------ SCAMS
    "digital_arrest": {
        "en": [
            "This is {agency}. A parcel in your name containing illegal items was seized at {city} airport. Case no {case_id}. Stay on this video call and do not inform anyone or you will be arrested.",
            "Your Aadhaar number is linked to a money laundering case. {agency} has issued an arrest warrant. Transfer Rs {amount} to the RBI verification account {acct} to clear your name.",
            "Officer from {agency} speaking. Your mobile number {phone} will be blocked in 2 hours due to illegal activity. Join the Skype call now for digital investigation.",
            "You are under digital arrest. Do not disconnect the call. Deposit Rs {amount} as security in the safe account, it will be refunded after verification.",
        ],
        "hi-en": [
            "Main {agency} se bol raha hoon. Aapke naam ka parcel {city} airport pe pakda gaya hai, usme drugs mile hain. Call cut mat karna, warna arrest hoga.",
            "Aapka Aadhaar money laundering case mein linked hai. Case {case_id}. Abhi Rs {amount} verification account {acct} mein transfer karo, kisi ko mat batana.",
            "Aap digital arrest mein ho. Video call band mat karo. Rs {amount} security deposit bhejo, verification ke baad refund ho jayega.",
            "{agency} notice: aapke number {phone} se illegal activity hui hai. 2 ghante mein number block hoga. Turant officer se baat karo.",
        ],
        "hi": [
            "मैं {agency} से बोल रहा हूँ। आपके नाम का पार्सल {city} एयरपोर्ट पर पकड़ा गया है जिसमें ड्रग्स मिले हैं। कॉल मत काटिए वरना गिरफ्तारी होगी।",
            "आपका आधार मनी लॉन्ड्रिंग केस से जुड़ा है। केस नंबर {case_id}। तुरंत ₹{amount} सत्यापन खाते {acct} में भेजें और किसी को न बताएं।",
            "आप डिजिटल अरेस्ट में हैं। वीडियो कॉल बंद न करें। ₹{amount} सुरक्षा राशि जमा करें, जांच के बाद वापस मिल जाएगी।",
            "{agency} सूचना: आपके नंबर {phone} से अवैध गतिविधि हुई है। 2 घंटे में नंबर बंद कर दिया जाएगा।",
        ],
    },
    "kyc_refund": {
        "en": [
            "Dear {bank} customer, your KYC has expired and your account will be blocked today. Update now: {link}",
            "Your {bank} account is suspended due to incomplete PAN/KYC. Call {phone} or click {link} to reactivate within 24 hours.",
            "Customer care: to process your refund of Rs {amount}, install AnyDesk and share the 9 digit code with our executive.",
            "Electricity bill not updated. Your power connection will be disconnected tonight at 9:30 PM. Contact officer {phone} immediately.",
        ],
        "hi-en": [
            "Dear customer, aapka {bank} KYC expire ho gaya hai. Aaj account block ho jayega. Abhi update karein: {link}",
            "Aapka refund Rs {amount} pending hai. Refund lene ke liye AnyDesk install karke code share karo.",
            "Bijli bill update nahi hua, aaj raat 9:30 baje connection kat jayega. Turant {phone} pe call karo.",
            "{bank} alert: PAN link nahi hai, account suspend. {link} pe details bharo 24 ghante ke andar.",
        ],
        "hi": [
            "प्रिय ग्राहक, आपका {bank} केवाईसी समाप्त हो गया है। आज खाता बंद हो जाएगा। तुरंत अपडेट करें: {link}",
            "आपका ₹{amount} का रिफंड लंबित है। रिफंड पाने के लिए ऐप इंस्टॉल करें और कोड साझा करें।",
            "बिजली बिल अपडेट नहीं हुआ है, आज रात 9:30 बजे कनेक्शन काट दिया जाएगा। तुरंत {phone} पर संपर्क करें।",
            "{bank} सूचना: पैन लिंक नहीं है, खाता निलंबित। 24 घंटे में {link} पर विवरण भरें।",
        ],
    },
    "lottery": {
        "en": [
            "Congratulations! Your number won Rs {prize} in the {brand} Lucky Draw. Pay processing fee of Rs {amount} to claim.",
            "KBC lottery winner! You have won Rs {prize}. Contact {name} at {phone} and pay GST Rs {amount} to release the prize.",
            "You have been selected for a free {gift}. Just pay delivery charges Rs {amount} to {vpa}.",
            "Dear user, your SIM won Rs {prize} in the anniversary bonanza. Claim before midnight: {link}",
        ],
        "hi-en": [
            "Badhai ho! Aapne {brand} lucky draw mein Rs {prize} jeete hain. Claim karne ke liye Rs {amount} processing fee bhejein.",
            "KBC se {mname} bol raha hoon, aapki Rs {prize} ki lottery lagi hai. GST Rs {amount} pay karo.",
            "Aapko free {gift} mila hai! Bas delivery charge Rs {amount} {vpa} pe bhejo.",
            "Aapke SIM number ne Rs {prize} jeete. Aaj raat tak claim karo: {link}",
        ],
        "hi": [
            "बधाई हो! आपने {brand} लकी ड्रा में ₹{prize} जीते हैं। दावा करने के लिए ₹{amount} प्रोसेसिंग शुल्क भेजें।",
            "केबीसी लॉटरी विजेता! आपने ₹{prize} जीते हैं। इनाम पाने के लिए ₹{amount} जीएसटी जमा करें।",
            "आपको मुफ्त {gift} मिला है। बस ₹{amount} डिलीवरी शुल्क {vpa} पर भेजें।",
            "आपके सिम नंबर ने ₹{prize} जीते हैं। आज रात तक दावा करें: {link}",
        ],
    },
    "upi_collect": {
        "en": [
            "Hi, I am buying your {item} listed on OLX. I have sent a collect request of Rs {amount}, enter your UPI PIN to receive the money.",
            "Payment of Rs {amount} received from {name}. Approve the request on your UPI app to credit it to your account.",
            "I am an army officer, sending advance Rs {amount} for the {item}. Accept the request from {vpa} and enter PIN.",
            "Cashback of Rs {amount} is waiting for you. Scan the QR code and enter your PIN to receive it.",
        ],
        "hi-en": [
            "Bhai main aapka {item} OLX pe kharid raha hoon. Rs {amount} ki request bheji hai, PIN daalo paise aa jayenge.",
            "Aapko {name} se Rs {amount} mile hain. App mein request approve karo, account mein credit ho jayega.",
            "Main army se hoon, {item} ke liye advance Rs {amount} bhej raha hoon. {vpa} ki request accept karo.",
            "Cashback Rs {amount} aapka wait kar raha hai. QR scan karke PIN daalo.",
        ],
        "hi": [
            "मैं आपका {item} खरीदना चाहता हूँ। ₹{amount} की रिक्वेस्ट भेजी है, पैसे पाने के लिए पिन डालें।",
            "आपको {name} से ₹{amount} प्राप्त हुए हैं। खाते में जमा करने के लिए ऐप में रिक्वेस्ट स्वीकार करें।",
            "मैं सेना में अधिकारी हूँ, {item} के लिए ₹{amount} अग्रिम भेज रहा हूँ। {vpa} की रिक्वेस्ट स्वीकार करें।",
            "₹{amount} का कैशबैक आपका इंतज़ार कर रहा है। क्यूआर स्कैन करें और पिन डालें।",
        ],
    },
    "job_task": {
        "en": [
            "Hello! We are hiring part-time from home. Earn Rs {earn} daily by liking {platform} videos. Interested? Reply YES.",
            "Your task #{task} is complete, commission Rs {earn} credited. To unlock the next premium task, deposit Rs {amount}.",
            "HR {name} from {company} here. Simple online rating job, 30 minutes a day, salary Rs {earn} per day. Join our Telegram group.",
            "Dear member, your account balance is frozen. Complete 3 more prepaid tasks of Rs {amount} to withdraw your earnings.",
        ],
        "hi-en": [
            "Hi! Ghar baithe part time job. {platform} videos like karke roz Rs {earn} kamao. Interested ho to YES likho.",
            "Task {task} complete, Rs {earn} commission mila. Next task unlock karne ke liye Rs {amount} deposit karo.",
            "Main {company} se HR {name}. Online rating ka kaam hai, roz 30 min, Rs {earn} per day. Telegram group join karo.",
            "Aapka balance freeze hai. Withdraw karne ke liye Rs {amount} ke 3 prepaid task aur complete karo.",
        ],
        "hi": [
            "नमस्ते! घर बैठे पार्ट टाइम नौकरी। {platform} वीडियो लाइक करके रोज़ ₹{earn} कमाएं। रुचि हो तो हाँ लिखें।",
            "टास्क {task} पूरा हुआ, ₹{earn} कमीशन मिला। अगला टास्क खोलने के लिए ₹{amount} जमा करें।",
            "मैं {company} से एचआर {fname} बोल रही हूँ। ऑनलाइन रेटिंग का काम, रोज़ 30 मिनट, ₹{earn} प्रतिदिन।",
            "आपका बैलेंस फ्रीज़ है। निकासी के लिए ₹{amount} के 3 प्रीपेड टास्क और पूरे करें।",
        ],
    },
    # ----------------------------------------------------------------- BENIGN
    "otp_notice": {
        "en": [
            "{otp} is your OTP for login to {bank} NetBanking. Valid for 10 minutes. Do not share it with anyone.",
            "Use OTP {otp} to complete your payment of Rs {amount} at {merchant}. Never share your OTP, {bank} will never ask for it.",
        ],
        "hi-en": [
            "Aapka {bank} OTP {otp} hai. Kisi ke saath share na karein.",
            "OTP {otp} se Rs {amount} ka payment {merchant} pe complete karein. Bank kabhi OTP nahi maangta.",
        ],
        "hi": [
            "{otp} आपका {bank} ओटीपी है। 10 मिनट के लिए मान्य। इसे किसी के साथ साझा न करें।",
            "{merchant} पर ₹{amount} के भुगतान के लिए ओटीपी {otp} है। बैंक कभी ओटीपी नहीं मांगता।",
        ],
    },
    "delivery": {
        "en": [
            "Your {merchant} order with {item} has been shipped via {courier}. Track: {blink}",
            "{courier}: Your parcel will be delivered today between 2 PM and 6 PM. Delivery code {otp}.",
            "Out for delivery: your order will arrive today. Pay Rs {amount} cash on delivery if applicable.",
        ],
        "hi-en": [
            "Aapka {merchant} order {courier} se ship ho gaya hai. Track karein: {blink}",
            "{courier}: aapka parcel aaj 2 se 6 baje ke beech deliver hoga. Code {otp}.",
            "Aapka order aaj aa jayega. COD hai to Rs {amount} ready rakhein.",
        ],
        "hi": [
            "आपका {merchant} ऑर्डर {courier} से भेज दिया गया है। ट्रैक करें: {blink}",
            "{courier}: आपका पार्सल आज दोपहर 2 से 6 बजे के बीच पहुंचेगा। कोड {otp}।",
            "आपका ऑर्डर आज पहुंचेगा। कैश ऑन डिलीवरी हो तो ₹{amount} तैयार रखें।",
        ],
    },
    "family_chat": {
        "en": [
            "Hey, reached home safely. Will call you after dinner.",
            "Mom, please send Rs {amount} for my college fees, deadline is tomorrow.",
            "Can you transfer Rs {amount} for the groceries? I paid at the store already.",
            "Happy birthday {name}! Party at 8 tonight, don't be late.",
        ],
        "hi-en": [
            "Ghar pahunch gaya, dinner ke baad call karta hoon.",
            "Mummy college fees ke liye Rs {amount} bhej do, kal last date hai.",
            "Sabzi ke Rs {amount} bhej dena, maine de diye the.",
            "Happy birthday {name}! Aaj raat 8 baje party hai.",
        ],
        "hi": [
            "घर पहुँच गया, खाने के बाद फोन करता हूँ।",
            "मम्मी, कॉलेज फीस के लिए ₹{amount} भेज दो, कल आखिरी तारीख है।",
            "सब्ज़ी के ₹{amount} भेज देना, मैंने दे दिए थे।",
            "जन्मदिन मुबारक हो {name}! आज रात 8 बजे पार्टी है।",
        ],
    },
    "bank_genuine": {
        "en": [
            "Dear customer, Rs {amount} has been debited from your {bank} account XX{last4} on {date}. Not you? Call the number on the back of your card.",
            "{bank}: Your KYC is due for periodic update. Please visit your nearest branch or update via the official app. We never ask for OTP or PIN.",
            "Rs {amount} credited to your {bank} a/c XX{last4} by UPI ref {ref}. Available balance updated.",
        ],
        "hi-en": [
            "{bank}: aapke account XX{last4} se Rs {amount} debit hua. Aap nahi the? Card ke peeche diye number pe call karein.",
            "{bank}: KYC update ke liye nazdiki branch jayein ya official app use karein. Hum kabhi OTP ya PIN nahi maangte.",
            "Aapke {bank} a/c XX{last4} mein Rs {amount} UPI se credit hua. Ref {ref}.",
        ],
        "hi": [
            "{bank}: आपके खाते XX{last4} से ₹{amount} डेबिट हुए। आपने नहीं किया? कार्ड के पीछे दिए नंबर पर कॉल करें।",
            "{bank}: केवाईसी अपडेट के लिए नज़दीकी शाखा जाएं या आधिकारिक ऐप का उपयोग करें। हम कभी ओटीपी या पिन नहीं मांगते।",
            "आपके {bank} खाते XX{last4} में ₹{amount} यूपीआई से जमा हुए। संदर्भ {ref}।",
        ],
    },
    "merchant_bill": {
        "en": [
            "Thank you for shopping at {merchant}. Your bill of Rs {amount} is paid.",
            "Your electricity bill of Rs {amount} for this month is generated. Due date {date}. Pay via the official app.",
            "Recharge of Rs {amount} successful for {phone}. Validity 28 days.",
        ],
        "hi-en": [
            "{merchant} pe shopping ke liye dhanyavaad. Rs {amount} ka bill paid.",
            "Is mahine ka bijli bill Rs {amount} hai. Last date {date}.",
            "{phone} pe Rs {amount} ka recharge successful.",
        ],
        "hi": [
            "{merchant} पर खरीदारी के लिए धन्यवाद। ₹{amount} का बिल भुगतान हो गया।",
            "इस महीने का बिजली बिल ₹{amount} है। अंतिम तिथि {date}।",
            "{phone} पर ₹{amount} का रिचार्ज सफल रहा।",
        ],
    },
    "refund_genuine": {
        "en": [
            "Refund of Rs {amount} for your {merchant} order has been initiated to your original payment method. It will reflect in 5-7 days.",
            "Your refund of Rs {amount} has been credited. No action is needed from your side.",
        ],
        "hi-en": [
            "Aapke {merchant} order ka Rs {amount} refund initiate ho gaya hai, 5-7 din mein aa jayega.",
            "Rs {amount} refund credit ho gaya, aapko kuch karne ki zarurat nahi.",
        ],
        "hi": [
            "आपके {merchant} ऑर्डर का ₹{amount} रिफंड शुरू कर दिया गया है, 5-7 दिन में मिल जाएगा।",
            "₹{amount} का रिफंड जमा हो गया है, आपको कुछ करने की ज़रूरत नहीं।",
        ],
    },
    "job_genuine": {
        "en": [
            "Hi {name}, thanks for applying to {company}. Your interview is scheduled on {date} at 11 AM. Please carry your resume.",
            "Your offer letter from {company} has been sent to your registered email. Please do not pay anyone for this job, we never charge candidates.",
        ],
        "hi-en": [
            "Hi {name}, {company} mein apply karne ke liye thanks. Interview {date} ko 11 baje hai.",
            "{company} ka offer letter aapke email pe bhej diya hai. Hum kabhi paise nahi maangte.",
        ],
        "hi": [
            "नमस्ते {name}, {company} में आवेदन के लिए धन्यवाद। आपका साक्षात्कार {date} को सुबह 11 बजे है।",
            "{company} का ऑफ़र लेटर आपके ईमेल पर भेज दिया गया है। हम उम्मीदवारों से कभी पैसे नहीं लेते।",
        ],
    },
}

# Slot fillers. A value is either a list (all languages) or a dict lang -> list.
FILLERS = {
    "name": ["Rahul", "Priya", "Amit", "Sneha", "Vikram", "Anjali", "Suresh", "Pooja", "Rohan", "Neha"],
    "mname": ["Rahul", "Amit", "Vikram", "Suresh", "Rohan"],     # used with masculine verbs
    "fname": ["Priya", "Sneha", "Anjali", "Pooja", "Neha"],      # used with feminine verbs
    "telco": ["Airtel", "Jio", "Vi", "BSNL"],
    "bank": ["SBI", "HDFC", "ICICI", "Axis", "PNB", "Kotak", "Bank of Baroda"],
    "agency": {
        "en": ["CBI", "Mumbai Police Cyber Cell", "Customs Department", "Narcotics Control Bureau", "TRAI", "Enforcement Directorate"],
        "hi-en": ["CBI", "Mumbai Police Cyber Cell", "Customs Department", "Narcotics Bureau", "TRAI"],
        "hi": ["सीबीआई", "मुंबई पुलिस साइबर सेल", "कस्टम विभाग", "नारकोटिक्स ब्यूरो", "ट्राई"],
    },
    "city": {
        "en": ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Kolkata", "Hyderabad"],
        "hi-en": ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Kolkata", "Hyderabad"],
        "hi": ["मुंबई", "दिल्ली", "बेंगलुरु", "चेन्नई", "कोलकाता", "हैदराबाद"],
    },
    "gift": {
        "en": ["iPhone 15", "smart TV", "gold coin", "laptop"],
        "hi-en": ["iPhone 15", "smart TV", "gold coin", "laptop"],
        "hi": ["आईफोन", "स्मार्ट टीवी", "सोने का सिक्का", "लैपटॉप"],
    },
    "item": {
        "en": ["sofa", "bike", "laptop", "fridge", "phone"],
        "hi-en": ["sofa", "bike", "laptop", "fridge", "phone"],
        "hi": ["सोफा", "बाइक", "लैपटॉप", "फ्रिज", "फोन"],
    },
    "brand": ["Jio", "Airtel", "Flipkart", "Amazon", "Tata"],
    # Same company list for job scams and genuine jobs, so the name itself is not a label leak
    "company": ["Amazon", "Flipkart", "Infosys", "Meesho", "TCS", "Wipro"],
    "merchant": ["Amazon", "Flipkart", "Big Bazaar", "Reliance Fresh", "Swiggy", "Zomato", "Myntra"],
    "courier": ["Blue Dart", "Delhivery", "India Post", "DTDC", "Ekart"],
    "platform": ["YouTube", "Instagram", "Google Maps"],
    "prize": ["25,00,000", "10,00,000", "5,00,000", "1,00,00,000", "50,000"],
    "link": ["kyc-update-now.co/verify", "bank-secure-login.xyz", "bit.ly/kyc-upd8", "claim-reward.in/win", "sbi-verify-kyc.top"],
    "blink": ["amzn.in/d/8xK2", "fkrt.it/track92", "track.delhivery.com/p/55", "indiapost.gov.in/track"],
}


# ---------------------------------------------------------------------------------------
# v2 additions (appended so existing template IDs keep their numbers).
# Written AFTER data/handwritten_test.csv was frozen; that file is never used for training.
# Benign hard negatives first: OTP notices, debit/credit alerts, bills, delivery -> 8+ per language.
# Scam families: +4 per language with different sentence structure.
# ---------------------------------------------------------------------------------------
EXTRA_TEMPLATES = {
    "otp_notice": {
        "en": [
            "Your OTP to verify your mobile number on {merchant} is {otp}. It expires in 5 minutes.",
            "{bank}: OTP {otp} for adding a new beneficiary. If this was not you, contact the branch. Never disclose OTP.",
            "Login attempt on your {merchant} account. Code: {otp}. Ignore if it was you.",
            "{otp} - one time password for e-mandate registration with {bank}. Valid 10 min. Do not share.",
            "Dear user, use {otp} to verify your email change request. This code is confidential.",
            "Transaction OTP {otp} for Rs {amount} on {bank} card XX{last4}. Call customer care if not initiated by you.",
        ],
        "hi-en": [
            "{merchant} pe mobile verify karne ka code {otp} hai, 5 min mein expire hoga.",
            "{bank}: naya beneficiary jodne ke liye OTP {otp}. Aapne request nahi ki to branch se sampark karein.",
            "Aapke {merchant} account mein login ki koshish hui. Code {otp}. Agar aap the to ignore karein.",
            "{otp} e-mandate registration ka OTP hai, {bank}. 10 minute valid. Kisi ko na dein.",
            "Rs {amount} ke card payment ke liye OTP {otp}, card XX{last4}. Agar aapne nahi kiya to customer care ko call karein.",
            "Email badalne ke liye verification code {otp} hai. Ise gupt rakhein.",
        ],
        "hi": [
            "{merchant} पर मोबाइल नंबर सत्यापित करने का कोड {otp} है। 5 मिनट में समाप्त होगा।",
            "{bank}: नया लाभार्थी जोड़ने के लिए ओटीपी {otp}। अनुरोध आपने नहीं किया तो शाखा से संपर्क करें।",
            "आपके {merchant} खाते में लॉगिन का प्रयास हुआ। कोड {otp}। यदि यह आप थे तो अनदेखा करें।",
            "{bank} ई-मैंडेट पंजीकरण के लिए ओटीपी {otp} है। 10 मिनट मान्य। किसी को न दें।",
            "कार्ड XX{last4} से ₹{amount} के भुगतान का ओटीपी {otp} है। लेन-देन आपने नहीं किया तो ग्राहक सेवा को कॉल करें।",
            "ईमेल बदलने का सत्यापन कोड {otp} है। इसे गोपनीय रखें।",
        ],
    },
    # bank_genuine numbering after this merge: 01 debit, 02 KYC reminder, 03 credit,
    # 04 debit, 05 credit, 06 debit, 07 credit, 08 debit, 09 credit  (see CREDIT_TEMPLATE_INDEX)
    "bank_genuine": {
        "en": [
            "Rs {amount} withdrawn at {bank} ATM from a/c XX{last4} on {date}. If not done by you, block your card via the official app.",
            "Salary of Rs {amount} credited to {bank} a/c XX{last4} on {date}. Avl bal updated.",
            "Your EMI of Rs {amount} for loan XX{last4} has been auto-debited. Thank you for banking with {bank}.",
            "IMPS credit of Rs {amount} received in a/c XX{last4} from {name}. Ref {ref}. -{bank}",
            "Autopay of Rs {amount} for {merchant} subscription debited from {bank} a/c XX{last4}.",
            "Interest of Rs {amount} credited to your {bank} savings account XX{last4} for the quarter.",
        ],
        "hi-en": [
            "{bank} ATM se a/c XX{last4} se Rs {amount} nikale gaye, {date}. Aapne nahi kiya to app se card block karein.",
            "Salary Rs {amount} aapke {bank} a/c XX{last4} mein credit hui, {date}.",
            "Loan XX{last4} ki EMI Rs {amount} auto-debit ho gayi. {bank}",
            "{name} se Rs {amount} IMPS se aapke a/c XX{last4} mein aaye. Ref {ref}.",
            "{merchant} subscription ka autopay Rs {amount} {bank} a/c XX{last4} se kata.",
            "Is quarter ka byaaj Rs {amount} aapke {bank} savings a/c XX{last4} mein credit hua.",
        ],
        "hi": [
            "{date} को {bank} एटीएम से खाता XX{last4} से ₹{amount} निकाले गए। आपने नहीं निकाले तो ऐप से कार्ड ब्लॉक करें।",
            "{date} को आपके {bank} खाते XX{last4} में ₹{amount} वेतन जमा हुआ।",
            "ऋण XX{last4} की ₹{amount} ईएमआई स्वतः कट गई है। {bank}",
            "{name} से ₹{amount} आईएमपीएस द्वारा आपके खाते XX{last4} में प्राप्त हुए। संदर्भ {ref}।",
            "{merchant} सदस्यता के लिए ₹{amount} का ऑटोपे {bank} खाते XX{last4} से कटा।",
            "इस तिमाही का ब्याज ₹{amount} आपके {bank} बचत खाते XX{last4} में जमा हुआ।",
        ],
    },
    "merchant_bill": {
        "en": [
            "Your {telco} mobile bill for this month is Rs {amount}. Last date to pay is {date}.",
            "Gas bill for this month: Rs {amount}. Pay before {date} through the official app or website.",
            "Property tax instalment of Rs {amount} is payable by {date}. Use the municipal website to pay.",
            "Payment received: Rs {amount} towards your broadband bill. Thank you.",
            "Your {telco} DTH pack of Rs {amount} renews on {date}. Recharge from the app to continue.",
        ],
        "hi-en": [
            "{telco} mobile ka is mahine ka bill Rs {amount}. Bharne ki aakhri tareekh {date}.",
            "Is mahine ka gas bill Rs {amount} hai, {date} se pehle official app se pay karein.",
            "Property tax ki kisht Rs {amount} {date} tak bharni hai, municipal website se.",
            "Broadband bill ke Rs {amount} mil gaye, dhanyavaad.",
            "{telco} DTH pack Rs {amount} ka {date} ko renew hoga. App se recharge karein.",
        ],
        "hi": [
            "आपका {telco} मोबाइल बिल इस महीने ₹{amount} है। भुगतान की अंतिम तिथि {date}।",
            "इस महीने का गैस बिल ₹{amount} है। {date} से पहले आधिकारिक ऐप से भुगतान करें।",
            "संपत्ति कर की ₹{amount} की किस्त {date} तक देय है। नगर निगम वेबसाइट से भुगतान करें।",
            "ब्रॉडबैंड बिल के ₹{amount} प्राप्त हुए, धन्यवाद।",
            "{telco} डीटीएच पैक ₹{amount} का {date} को नवीनीकृत होगा। ऐप से रिचार्ज करें।",
        ],
    },
    "delivery": {
        "en": [
            "{courier}: your shipment {ref} is in transit and will reach your city tomorrow.",
            "Your {merchant} package was delivered at the front door. Rate your delivery experience in the app.",
            "{courier} could not deliver your parcel as the address was locked. Reschedule from the tracking page.",
            "Return pickup for your {merchant} order is scheduled for {date}. Keep the item packed.",
            "Your {merchant} order {ref} has been packed and will be handed to {courier} today.",
        ],
        "hi-en": [
            "{courier}: aapka shipment {ref} raste mein hai, kal aapke sheher pahunchega.",
            "Aapka {merchant} package darwaze pe deliver ho gaya. App mein rating dein.",
            "Ghar band hone ki wajah se {courier} parcel deliver nahi kar paya. Tracking page se naya time chunein.",
            "{merchant} order ka return pickup {date} ko hai, item pack karke rakhein.",
            "{merchant} order {ref} pack ho gaya hai, aaj {courier} ko diya jayega.",
        ],
        "hi": [
            "{courier}: आपका शिपमेंट {ref} रास्ते में है और कल आपके शहर पहुंचेगा।",
            "आपका {merchant} पैकेज दरवाज़े पर पहुंचा दिया गया है। ऐप में अनुभव रेट करें।",
            "पता बंद होने के कारण {courier} पार्सल नहीं पहुंचा सका। ट्रैकिंग पेज से समय दोबारा चुनें।",
            "{merchant} ऑर्डर का रिटर्न पिकअप {date} को है। सामान पैक रखें।",
            "{merchant} ऑर्डर {ref} पैक हो गया है, आज {courier} को सौंपा जाएगा।",
        ],
    },
    "digital_arrest": {
        "en": [
            "Notice from {agency}: SIM cards issued on your Aadhaar are linked to {case_id}. Officers will contact you shortly. Non-cooperation will lead to immediate arrest.",
            "We have frozen your accounts as part of a narcotics probe. To verify your funds are legal, move Rs {amount} to the supervised account {acct} today.",
            "Stay where you are and keep the video on. Leaving the call or telling family will be treated as obstruction of justice.",
            "Court summons {case_id}: you are named in a cyber fraud FIR. Pay the bail bond of Rs {amount} online to avoid custody.",
        ],
        "hi-en": [
            "{agency} ki taraf se: aapke Aadhaar pe nikle SIM ek case {case_id} se jude hain. Sahyog nahi kiya to turant giraftari.",
            "Narcotics jaanch ke chalte aapke account freeze hain. Paisa legal hai ye saabit karne ke liye Rs {amount} supervised account {acct} mein daalo.",
            "Jahan ho wahin raho, camera on rakho. Call chhoda ya ghar walon ko bataya to kanooni karyavahi hogi.",
            "Court ka summon {case_id}: FIR mein aapka naam hai. Custody se bachne ke liye Rs {amount} bail bond online bharo.",
        ],
        "hi": [
            "{agency} की ओर से सूचना: आपके आधार पर जारी सिम केस {case_id} से जुड़े हैं। सहयोग न करने पर तुरंत गिरफ्तारी होगी।",
            "नशीले पदार्थों की जांच के चलते आपके खाते फ्रीज़ हैं। धन वैध साबित करने के लिए आज ₹{amount} निगरानी खाते {acct} में डालें।",
            "जहां हैं वहीं रहें और कैमरा चालू रखें। कॉल छोड़ना या परिवार को बताना न्याय में बाधा माना जाएगा।",
            "अदालत का समन {case_id}: एफआईआर में आपका नाम है। हिरासत से बचने के लिए ₹{amount} जमानत राशि ऑनलाइन भरें।",
        ],
    },
    "kyc_refund": {
        "en": [
            "{bank} netbanking will be disabled at midnight as your PAN is not linked. Complete verification here: {link}",
            "Hi, this is {bank} support. To reverse the failed debit of Rs {amount}, open the screen-sharing app we sent and read out the code.",
            "Your pension of Rs {amount} is on hold because the life certificate expired. Update it at {link} to restart payments.",
            "Dear customer, a refund of Rs {amount} is waiting. Our agent will call you; keep the verification code ready to tell him.",
        ],
        "hi-en": [
            "PAN link nahi hone se {bank} netbanking aaj raat band ho jayegi. Yahan verify karein: {link}",
            "{bank} support se bol rahe hain. Rs {amount} ka failed debit wapas karne ke liye bheja hua screen share app kholo aur code batao.",
            "Life certificate expire hone se aapki pension Rs {amount} ruki hai. {link} pe update karo tabhi paisa aayega.",
            "Rs {amount} ka refund wait kar raha hai. Hamara agent call karega, verification code bata dena.",
        ],
        "hi": [
            "पैन लिंक न होने से {bank} नेट बैंकिंग आज रात बंद हो जाएगी। यहां सत्यापन करें: {link}",
            "{bank} सहायता से बोल रहे हैं। ₹{amount} की असफल कटौती वापस पाने के लिए भेजा गया स्क्रीन शेयर ऐप खोलें और कोड बताएं।",
            "जीवन प्रमाण पत्र की अवधि खत्म होने से आपकी ₹{amount} पेंशन रुकी है। {link} पर अपडेट करें।",
            "₹{amount} का रिफंड आपका इंतज़ार कर रहा है। हमारा एजेंट कॉल करेगा, सत्यापन कोड बता दें।",
        ],
    },
    "lottery": {
        "en": [
            "Your number is today's winner in the {brand} Golden Week contest. Reward: Rs {prize}. A one-time verification charge of Rs {amount} applies.",
            "Prize department: the {gift} you won is packed. Release it from the warehouse by paying insurance of Rs {amount} to {vpa}.",
            "Final reminder, Rs {prize} is still unclaimed in your name. Send the claim fee before midnight or it goes to the next winner.",
            "{name}, you are 1 of 10 lucky users selected by {brand}. Tap {link} and complete the payment step to receive Rs {prize}.",
        ],
        "hi-en": [
            "Aaj ke {brand} Golden Week contest mein aapka number jeeta hai. Inaam Rs {prize}. Ek baar ka verification charge Rs {amount} lagega.",
            "Aapka jeeta hua {gift} pack ho gaya hai. Warehouse se release ke liye Rs {amount} insurance {vpa} pe bhejo.",
            "Aakhri reminder, Rs {prize} aapke naam pe abhi bhi pada hai. Aadhi raat se pehle claim fee bhejo warna agle winner ko jayega.",
            "{name}, {brand} ne aapko 10 lucky users mein chuna hai. {link} kholo aur payment step poora karke Rs {prize} pao.",
        ],
        "hi": [
            "आज के {brand} गोल्डन वीक प्रतियोगिता में आपका नंबर जीता है। इनाम ₹{prize}। एक बार का सत्यापन शुल्क ₹{amount} लगेगा।",
            "आपका जीता हुआ {gift} पैक हो गया है। गोदाम से छुड़ाने के लिए ₹{amount} बीमा {vpa} पर भेजें।",
            "अंतिम याद दिलाना: ₹{prize} अभी भी आपके नाम पर बाकी है। आधी रात से पहले दावा शुल्क भेजें।",
            "{name}, {brand} ने आपको 10 भाग्यशाली उपयोगकर्ताओं में चुना है। {link} खोलें और ₹{prize} पाने के लिए भुगतान पूरा करें।",
        ],
    },
    "upi_collect": {
        "en": [
            "Sir I am sending the token amount for your {item} through the app. You will see Rs {amount} pending, tap Pay and enter PIN to receive.",
            "Delivery partner here, your COD refund of Rs {amount} will come as a request. Accept it from {vpa} to get the money back.",
            "Your {brand} reward of Rs {amount} is ready. Open the payment request from {vpa} and authorise it to get the money.",
            "To receive your security deposit refund of Rs {amount}, scan the QR I just sent and confirm with your UPI PIN.",
        ],
        "hi-en": [
            "Sir {item} ka token amount app se bhej raha hoon. Rs {amount} pending dikhega, Pay dabake PIN daalo paise mil jayenge.",
            "Delivery partner bol raha hoon, COD refund Rs {amount} request ke roop mein aayega. {vpa} ki request accept karo.",
            "Aapka {brand} reward Rs {amount} ready hai. {vpa} ki payment request kholke authorise karo, paise aa jayenge.",
            "Security deposit ke Rs {amount} wapas lene ke liye bheja hua QR scan karo aur UPI PIN se confirm karo.",
        ],
        "hi": [
            "सर, {item} की टोकन राशि ऐप से भेज रहा हूँ। ₹{amount} लंबित दिखेगा, पे दबाकर पिन डालें, पैसे मिल जाएंगे।",
            "डिलीवरी पार्टनर बोल रहा हूँ, ₹{amount} का सीओडी रिफंड रिक्वेस्ट के रूप में आएगा। {vpa} की रिक्वेस्ट स्वीकार करें।",
            "आपका {brand} इनाम ₹{amount} तैयार है। पैसे पाने के लिए {vpa} का भुगतान अनुरोध खोलकर अधिकृत करें।",
            "सिक्योरिटी डिपॉज़िट के ₹{amount} वापस पाने के लिए भेजा गया क्यूआर स्कैन करें और यूपीआई पिन से पुष्टि करें।",
        ],
    },
    "job_task": {
        "en": [
            "We found your profile on a job portal. Earn Rs {earn} a day rating hotels from your phone. Training is free, reply to begin.",
            "Level 2 unlocked! Recharge your task account with Rs {amount} to receive the next batch of orders and a 25% bonus.",
            "Withdrawal blocked: your credit score in the task app is low. Pay Rs {amount} to restore it and release your earnings.",
            "Daily payout job from {company}: 20 minutes of app reviews, Rs {earn} paid the same day. Message the coordinator on Telegram.",
        ],
        "hi-en": [
            "Job portal pe aapki profile mili. Phone se hotels ko rating dekar roz Rs {earn} kamao. Training free hai, reply karo.",
            "Level 2 unlock! Agle orders aur 25% bonus ke liye task account mein Rs {amount} recharge karo.",
            "Withdrawal ruka hai kyunki task app mein credit score kam hai. Rs {amount} bharo aur kamai release karo.",
            "{company} ki daily payout job: 20 minute app review, Rs {earn} usi din. Telegram pe coordinator ko message karo.",
        ],
        "hi": [
            "जॉब पोर्टल पर आपकी प्रोफ़ाइल मिली। फ़ोन से होटल को रेटिंग देकर रोज़ ₹{earn} कमाएं। प्रशिक्षण मुफ्त है।",
            "लेवल 2 खुल गया! अगले ऑर्डर और 25% बोनस के लिए टास्क खाते में ₹{amount} रिचार्ज करें।",
            "निकासी रुकी है क्योंकि टास्क ऐप में क्रेडिट स्कोर कम है। कमाई छुड़ाने के लिए ₹{amount} भरें।",
            "{company} की दैनिक भुगतान नौकरी: 20 मिनट ऐप समीक्षा, उसी दिन ₹{earn}। टेलीग्राम पर समन्वयक को संदेश भेजें।",
        ],
    },
}

for _key, _langs in EXTRA_TEMPLATES.items():
    for _lang, _items in _langs.items():
        TEMPLATES[_key][_lang].extend(_items)

# Benign templates whose paired transaction is money IN (direction = credit). 1-based template index.
# None = every template of that subtype.
CREDIT_TEMPLATE_INDEX = {"bank_genuine": {3, 5, 7, 9}, "refund_genuine": None}

# Rows to generate per key (v2). Hard-negative subtypes get more rows so each fold has
# several of their templates and FPR estimates are less noisy.
ROWS_PER_KEY = {
    "kyc_refund": 200, "digital_arrest": 200, "lottery": 200, "upi_collect": 200, "job_task": 200,
    "otp_notice": 200, "bank_genuine": 220, "merchant_bill": 200, "delivery": 200,
    "family_chat": 100, "refund_genuine": 100, "job_genuine": 100,
}
