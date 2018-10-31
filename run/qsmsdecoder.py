#!/usr/bin/python3
import binascii
mti_types = ('SMS-DELIVER','SMS-SUBMIT','SMS-COMMAND','SMS-STATUS-REPORT', 'UNKNOWN')

def decodeAddress(addr):
    num = list(addr)
    #print(num)
    for i in range(0, len(num), 2):
        num[i], num[i+1] = num[i+1], num[i]
    return (''.join(num).replace('F',''))

def encodeAddress(addr):
    num = list(addr)
    if len(num) %2 > 0:
        num.append('F')
    for i in range(0, len(num), 2):
        num[i], num[i+1] = num[i+1], num[i]
    return (''.join(num))

def decodeUTC2(str):
    return binascii.unhexlify(str).decode('utf-16-be')

def encodeUTC2(str):
    return binascii.hexlify(str.encode('utf-16-be')).decode()

def encodeGSM(str): #http://hardisoft.ru/soft/samodelkin-soft/otpravka-sms-soobshhenij-v-formate-pdu-teoriya-s-primerami-na-c-chast-2/
    arr = bytearray(str.encode())
    i = 1
    while i < len(arr):
        j = len(arr)-1
        while j >= i:
            #Count 0-bit of current byte
            firstBit = arr[j] % 2 << 7
            #and insert it in place of 7-bit of previous byte
            arr[j-1] = arr[j-1] & 0b01111111 | firstBit
            
            #Bitmoving current byte right for 1 bit
            arr[j] = arr[j] >> 1
            j -= 1
        i += 1
    
    arr = bytearray(filter(None, arr))
    res = binascii.hexlify(arr).decode()
    return res

def decodeGSM(gsmString): #http://hardisoft.ru/soft/samodelkin-soft/otpravka-sms-soobshhenij-v-formate-pdu-teoriya-s-primerami-na-c-chast-2/
    #n = int(len(gsmString)/8) + 2
    
    arr = bytearray(binascii.unhexlify(gsmString))
    for i in range(0, int(len(arr)/8)+3):
        arr.append(0)
    i = len(arr) - 2
    while i >= 0: #len(arr):
        j = i+1
        while j < len(arr):
            #Count 7-bit of previous byte
            firstBit = (arr[j-1] & 0b10000000) >> 7
            #and insert it in place of 0-bit of current byte
            arr[j] = (arr[j] << 1) & 0b11111110 | firstBit
            j += 1
        #arr[i] = arr[i] & 0b01111111 #Set first bit to zero
        i -= 1
    for i in range(0, len(arr)-1): #Clear 7-bits 
        arr[i] = arr[i] & 0b01111111
    arr = bytearray(filter(None, arr))
    return arr.decode()

def encodeSMS(address, text, instance=0, max_instance=0, sequence=0):
    #sca = '0791' + encodeAddress('79104999109')
    sca = '00'
    pdu_type = '01'
    mr = '{:x}'.format(instance).zfill(2)
    da_len = '{:x}'.format(len(address)).zfill(2)
    da_type = '91'
    da_msisdn = encodeAddress(address)
    tp_pid = '00'
    tp_dcs = '08'
    #if we need multi-part SMS, filling UDH block and setting bit 4 in pdu_type
    udh = ''
    if instance > 0:
        pdu_type = '41' #'33' #
        udh = '050003' + '{:x}'.format(sequence).zfill(2) + '{:x}'.format(max_instance).zfill(2) + '{:x}'.format(instance).zfill(2)
    ud = udh + binascii.hexlify(text.encode('utf-16-be')).decode()
    udl = '{:x}'.format(int(len(ud)/2)).zfill(2)
    msg = pdu_type + mr + da_len + da_type + da_msisdn + tp_pid + tp_dcs + udl + ud
    msg_len = len(msg)
    msg = sca + msg
    return {'message':msg, 'message_length':int(msg_len/2)}
    
def decodeSMS(pdu):
    is_long = False
    sc_len = int(pdu[0:2])
#    print('sc_len: %s' % sc_len)
    ta = int(pdu[2:4], 16)
    sca = decodeAddress(pdu[4:(sc_len+1)*2]) #+1 - the sc_len field itself
    #rearraging digits
    
    i0 = (sc_len+1)*2 #index of first TPDU octet
    pdu_type = int(pdu[i0:i0+2], 16) #First octet of TPDU
#    print('pdu_type: %s' % bin(pdu_type))
    mti = pdu_type & 0b11
    mtiString = mti_types[mti] #Message type
#    print('VPF: %d' % vpf)
    udhi = (pdu_type & 0b01000000) >> 6 # This bit shows if there is a header in user data
    sri = (pdu_type & 0b00100000) >> 5 #status request
    mms = (pdu_type & 0b00000100) >> 2 # More message 2 send for incoming or tp rd (reject duplicates) for outcoming messages
    i0 += 2
    vpf = 0
    #in outcoming messages there is additional byte 'message ID ranging' with usual 0xFF value
    if mti % 2 > 0:
        vpf = (pdu_type & 0b00011000) >> 3 # need to determine whever the VP field exists and its length
        mr = int(pdu[i0:i0+2], 16)
#        print('MR: %s' % mr)
        i0 += 2
        
    addr_len = int(pdu[i0:i0+2], 16) #Second octet is the Dest/source address length
#    print('%d: da_len=%d' % (i0, addr_len))
    addr_len += addr_len % 2 #adding 1 if address_len is odd
    ton_msisdn = int(pdu[i0+2:i0+4], 16) #Second octet of TPDU
    msisdn = decodeAddress(pdu[i0+4: i0+4+addr_len])
    i0 += 4+addr_len
#    print('%d: PID=%s' % (i0, pdu[i0:i0+2]))
    pid = int(pdu[i0:i0+2], 16)
    dcs = int(pdu[i0+2:i0+4], 16)
    i0 += 4
    if vpf > 0:
        vp = int(pdu[i0:i0+2], 16)
#        print('VP exists: %d' % vp)
        i0 += 2
    if mti % 2 == 0: # Incoming messages have a SMSC timestamp
        scts = pdu[i0:i0+12]
#        print('scts_len: %d' % len(scts))
        time = decodeAddress(scts)
        i0 += 12
        timezone = pdu[i0+1:i0-1:-1]
        i0 += 2
    udl = int(pdu[i0:i0+2],16)
    i0 += 2    #+udhl
    if udhi > 0: # if we have a header
        udhl = int(pdu[i0:i0+2], 16) # header length
        udh = pdu[i0+2:i0+2+udhl*2] #header source
        i = 0
        ieds = list()
        while i < udhl*2:
            iei = udh[i:i+2]
            iedl = int(udh[i+2:i+4], 16)
            ied1_len = 2
            if iei == '08':
                is_long=True
                ied1_len = 4
            else:
                if iei == '00':
                    is_long = True
            ied1 = udh[i+4:i+4+ied1_len] #ID of long message
            i += 4 + ied1_len
            ied2 = int(udh[i:i+2], 16) #Number of message parts
            ied3 = int(udh[i+2:i+4], 16) #Number of this message in queue
            ieds.append({'iei':iei, 'iedl':iedl, 'ied1':ied1, 'ied2':ied2,'ied3':ied3})
            i += 4
        i0 += 2 + udhl*2
    ud = pdu[i0:]
##    try:
##        if(dcs == 8):
##            text = binascii.unhexlify(ud).decode('utf-16-be')
##        else:
##            text = decodeGSM(ud)
##    except Exception as err:
##        text = ud
    res={'type_sca':ta, 'sca':sca, 'pdu_type': pdu_type, 'vpf':vpf, 'udhi':udhi, 'type_msisdn':ton_msisdn,\
         'msisdn':msisdn, 'mti':mtiString, 'mms':mms, 'sri':sri, 'pid':pid, 'dcs':dcs, 'udl':udl, 'ud':ud, 'is_long':is_long}
    if vpf > 0:
        res['vp'] = vp
    if udhi > 0:
        res['udhl'] = udhl
        res['udh'] = udh
        res['ieds'] = ieds
    if mti % 2 == 0:
        res['scts'] = scts
        res['time'] = time
        res['timezone'] = timezone
        res['sri'] = sri
    return res

def bySMSnum(x):
    return x['ieds'][0]['ied3']

def catSMS(gsmMessageList): #
    mlist = list()
    msg = gsmMessageList[0]
    if type(msg) == type('string'): #if message is unconverted GSM-string, convert it
        msg = decodeSMS(msg)
    mlist.append(msg)
    gsmMessageList.remove(gsmMessageList[0])
    if not msg['is_long']: #if message is simple return nothing
        return None
    ins_max = msg['ieds'][0]['ied2']
    ins_num = msg['ieds'][0]['ied3']
    sequence = msg['ieds'][0]['ied1']
    for m in gsmMessageList:
        mnew = m
        if type(m) == type('string'):
            mnew = decodeSMS(mnew)
        if sequence == mnew['ieds'][0]['ied1'] and ins_num != mnew['ieds'][0]['ied3']: #if sequence number correlate and m is not msg
            mlist.append(mnew)
            gsmMessageList.remove(m)
    mlist = sorted(mlist, key = bySMSnum)
    #Now we have sorted list of one-sequence messages an original list cleared from its values
#    return mlist
    ud_sum = ''
    udl_sum = 0
    text = ''
    sequence_info = {'full':False, 'sequence':sequence, 'max': ins_max, 'worked': []} #setting sequence_info for fullness checking
    dcs = mlist[0]['dcs']
    if dcs == 0: #7-bit coding. Take the whole message with udh and udhl
        for m in mlist:
            print(m['ieds'][0])
            ud_full = '{:x}'.format(m['udhl']).zfill(2) + m['udh'] + m['ud']
            text += decodeGSM(ud_full)[m['udhl']:] #Drop first bytes (UDH)
            ud_sum += ud_full
            udl_sum += m['udl']
            sequence_info['worked'].append(m['ieds'][0]['ied3']) #number of instance in sequence
    else:
        for m in mlist:
            udl_sum += m['udl']
            ud_sum += m['ud']
            sequence_info['worked'].append(m['ieds'][0]['ied3']) #number of instance in sequence
        text = binascii.unhexlify(ud_sum).decode('utf-16-be')
    if len(sequence_info['worked']) == sequence_info['max']:
        sequence_info['full'] = True
    mres={'text':text, 'udl':udl_sum, 'ud':ud_sum, 'mlist':mlist, 'sequence_info':sequence_info}
#    print(sequence_info)
    return mres

gsm = encodeGSM('ClearSMS')
num = '79202599259'
large1 = '07919761980644F0440B919702529952F9000081905191707121A0050003FD02019861F9B9CC02D9CBF23C881D969FCBA076793E0F9FCB2E10332C3F9759207B599E07B1C3F27319D42ECFE7E173D9056286E5E7320B642FCBF32076587E2E83DAE5F93C7C2EBB40CCB0FC5C6681EC65791EC40ECBCF6550BB3C9F87CF65178819969FCB2C90BD2CCF83D861F9B90C6A97E7F3F0B9EC0231C3F2739905B297E579103B2C3F9741'
large2 = '07919761980644F0640B919702529952F900008190519170712161050003FD0202DAE5F93C7C2EBB40CCB0FC5C6681EC65791EC40ECBCF6550BB3C9F87CF65178819969FCB2C90BD2CCF83D861F9B90C6A97E7F3F0B9EC0231C3F2739905B297E579103B2C3F9741EDF27C1E3E975D20'

lrgrus1 = '07919761980644F0440B919702529952F90008819061112564218C050003110201041F043504400435043404300435043C0020043F044004380432043504420020043800200441043C043E044204400438043C002004420435043B0435043204380437043E0440002E0020041A0430043A00200431044B0432043004350442002004320020043D043004480435043C00200446043004400441044204320435002D0433043E0441'
lrgrus2 = '07919761980644F0640B919702529952F90008819061112574216005000311020204430434043004400441044204320435002C00200445043E04340438043C002004370430002004330440043804310430043C0438002004320020043F043E043B0435002004380020043D04300020044004350447043A0443002E'

msg1 = decodeSMS(lrgrus1)
msg2 = decodeSMS(lrgrus2)


llist = [large2, large1]
lrus = [lrgrus1, lrgrus2]
lmsg = [msg1, msg2]

txt = 'Абырвалг - это великое и мощное слово в русской литературе. Его значимость трудно переоценить.'
addr = '79202599259'


