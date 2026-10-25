import type { Language, ScamFamily } from '../types'

/** Synthetic, already-redacted message samples used by the mock API and presets. */
export const SAMPLE_MESSAGES: Record<Exclude<ScamFamily, 'unknown'>, Partial<Record<Language, string[]>>> = {
  kyc_refund: {
    en: [
      'Dear customer, your bank KYC has expired and your account will be blocked today. Update KYC immediately at the link or call [PHONE].',
      'Your refund of Rs 2,340 is pending. Share the code [OTP] with our executive to process the refund now.',
    ],
    hinglish: ['Aapka KYC expire ho gaya hai, account band ho jayega. Turant update karo, call karo [PHONE].'],
    hi: ['प्रिय ग्राहक, आपका केवाईसी समाप्त हो गया है। खाता बंद हो जाएगा, तुरंत अपडेट करें।'],
  },
  digital_arrest: {
    en: ['This is CBI cyber cell. A parcel in your name has narcotics. You are under digital arrest. Stay on the video call and transfer funds for verification.'],
    hinglish: ['Main police se bol raha hoon, aapke naam pe case hai. Video call pe raho warna giraftar honge.'],
    hi: ['आपके नाम पर पार्सल में ड्रग्स मिले हैं। पुलिस जांच चल रही है, गिरफ्तार होने से बचने के लिए तुरंत भुगतान करें।'],
  },
  lottery: {
    en: ['Congratulations! You have won Rs 25,00,000 in the KBC lucky draw. Pay the processing fee to claim your prize.'],
    hinglish: ['Badhai ho! Aapne lottery jeeti hai, prize claim karne ke liye fee bhejo abhi.'],
  },
  upi_collect: {
    en: ['To receive the money for your OLX item, approve the collect request and enter your UPI PIN.'],
    hinglish: ['Paise receive karne ke liye request approve karo aur PIN daalo.'],
  },
  job_task: {
    en: ['Part-time job: earn Rs 3,000 daily by rating videos. Complete the prepaid task to unlock your commission.'],
    hinglish: ['Ghar baithe kamai! Daily task complete karo, pehle recharge task ka payment karo.'],
  },
  benign: {
    en: ['Your order has been shipped and will arrive tomorrow.', 'Will pay you back for dinner, thanks!'],
    hinglish: ['Bhai kal ka movie ticket ka paisa bhej raha hoon.'],
    hi: ['माँ, किराने का सामान ले आया हूँ।'],
  },
}

export const COACHED_VICTIM_MESSAGE = SAMPLE_MESSAGES.kyc_refund.en![0]
