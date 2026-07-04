/* poise-card 0.141.0 — bundled, served by the Poise integration (ADR-0040) */
var Y=globalThis,J=Y.ShadowRoot&&(Y.ShadyCSS===void 0||Y.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,ue=Symbol(),ke=new WeakMap,U=class{constructor(e,t,n){if(this._$cssResult$=!0,n!==ue)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,t=this.t;if(J&&e===void 0){let n=t!==void 0&&t.length===1;n&&(e=ke.get(t)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),n&&ke.set(t,e))}return e}toString(){return this.cssText}},Ee=o=>new U(typeof o=="string"?o:o+"",void 0,ue),F=(o,...e)=>{let t=o.length===1?o[0]:e.reduce((n,r,s)=>n+(i=>{if(i._$cssResult$===!0)return i.cssText;if(typeof i=="number")return i;throw Error("Value passed to 'css' function must be a 'css' function result: "+i+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(r)+o[s+1],o[0]);return new U(t,o,ue)},Pe=(o,e)=>{if(J)o.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of e){let n=document.createElement("style"),r=Y.litNonce;r!==void 0&&n.setAttribute("nonce",r),n.textContent=t.cssText,o.appendChild(n)}},he=J?o=>o:o=>o instanceof CSSStyleSheet?(e=>{let t="";for(let n of e.cssRules)t+=n.cssText;return Ee(t)})(o):o;var{is:at,defineProperty:lt,getOwnPropertyDescriptor:ct,getOwnPropertyNames:dt,getOwnPropertySymbols:pt,getPrototypeOf:ut}=Object,Z=globalThis,Me=Z.trustedTypes,ht=Me?Me.emptyScript:"",mt=Z.reactiveElementPolyfillSupport,N=(o,e)=>o,me={toAttribute(o,e){switch(e){case Boolean:o=o?ht:null;break;case Object:case Array:o=o==null?o:JSON.stringify(o)}return o},fromAttribute(o,e){let t=o;switch(e){case Boolean:t=o!==null;break;case Number:t=o===null?null:Number(o);break;case Object:case Array:try{t=JSON.parse(o)}catch{t=null}}return t}},Le=(o,e)=>!at(o,e),Re={attribute:!0,type:String,converter:me,reflect:!1,useDefault:!1,hasChanged:Le};Symbol.metadata??=Symbol("metadata"),Z.litPropertyMetadata??=new WeakMap;var $=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=Re){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let n=Symbol(),r=this.getPropertyDescriptor(e,n,t);r!==void 0&&lt(this.prototype,e,r)}}static getPropertyDescriptor(e,t,n){let{get:r,set:s}=ct(this.prototype,e)??{get(){return this[t]},set(i){this[t]=i}};return{get:r,set(i){let l=r?.call(this);s?.call(this,i),this.requestUpdate(e,l,n)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??Re}static _$Ei(){if(this.hasOwnProperty(N("elementProperties")))return;let e=ut(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(N("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(N("properties"))){let t=this.properties,n=[...dt(t),...pt(t)];for(let r of n)this.createProperty(r,t[r])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[n,r]of t)this.elementProperties.set(n,r)}this._$Eh=new Map;for(let[t,n]of this.elementProperties){let r=this._$Eu(t,n);r!==void 0&&this._$Eh.set(r,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let n=new Set(e.flat(1/0).reverse());for(let r of n)t.unshift(he(r))}else e!==void 0&&t.push(he(e));return t}static _$Eu(e,t){let n=t.attribute;return n===!1?void 0:typeof n=="string"?n:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let n of t.keys())this.hasOwnProperty(n)&&(e.set(n,this[n]),delete this[n]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Pe(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,n){this._$AK(e,n)}_$ET(e,t){let n=this.constructor.elementProperties.get(e),r=this.constructor._$Eu(e,n);if(r!==void 0&&n.reflect===!0){let s=(n.converter?.toAttribute!==void 0?n.converter:me).toAttribute(t,n.type);this._$Em=e,s==null?this.removeAttribute(r):this.setAttribute(r,s),this._$Em=null}}_$AK(e,t){let n=this.constructor,r=n._$Eh.get(e);if(r!==void 0&&this._$Em!==r){let s=n.getPropertyOptions(r),i=typeof s.converter=="function"?{fromAttribute:s.converter}:s.converter?.fromAttribute!==void 0?s.converter:me;this._$Em=r;let l=i.fromAttribute(t,s.type);this[r]=l??this._$Ej?.get(r)??l,this._$Em=null}}requestUpdate(e,t,n,r=!1,s){if(e!==void 0){let i=this.constructor;if(r===!1&&(s=this[e]),n??=i.getPropertyOptions(e),!((n.hasChanged??Le)(s,t)||n.useDefault&&n.reflect&&s===this._$Ej?.get(e)&&!this.hasAttribute(i._$Eu(e,n))))return;this.C(e,t,n)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,t,{useDefault:n,reflect:r,wrapped:s},i){n&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,i??t??this[e]),s!==!0||i!==void 0)||(this._$AL.has(e)||(this.hasUpdated||n||(t=void 0),this._$AL.set(e,t)),r===!0&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[r,s]of this._$Ep)this[r]=s;this._$Ep=void 0}let n=this.constructor.elementProperties;if(n.size>0)for(let[r,s]of n){let{wrapped:i}=s,l=this[r];i!==!0||this._$AL.has(r)||l===void 0||this.C(r,void 0,s,l)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(n=>n.hostUpdate?.()),this.update(t)):this._$EM()}catch(n){throw e=!1,this._$EM(),n}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};$.elementStyles=[],$.shadowRootOptions={mode:"open"},$[N("elementProperties")]=new Map,$[N("finalized")]=new Map,mt?.({ReactiveElement:$}),(Z.reactiveElementVersions??=[]).push("2.1.2");var xe=globalThis,He=o=>o,Q=xe.trustedTypes,Te=Q?Q.createPolicy("lit-html",{createHTML:o=>o}):void 0,Ne="$lit$",C=`lit$${Math.random().toFixed(9).slice(2)}$`,Ve="?"+C,ft=`<${Ve}>`,P=document,z=()=>P.createComment(""),B=o=>o===null||typeof o!="object"&&typeof o!="function",we=Array.isArray,_t=o=>we(o)||typeof o?.[Symbol.iterator]=="function",fe=`[ 	
\f\r]`,V=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Oe=/-->/g,De=/>/g,k=RegExp(`>|${fe}(?:([^\\s"'>=/]+)(${fe}*=${fe}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Ie=/'/g,Ue=/"/g,ze=/^(?:script|style|textarea|title)$/i,$e=o=>(e,...t)=>({_$litType$:o,strings:e,values:t}),f=$e(1),Be=$e(2),en=$e(3),M=Symbol.for("lit-noChange"),u=Symbol.for("lit-nothing"),Fe=new WeakMap,E=P.createTreeWalker(P,129);function Ke(o,e){if(!we(o)||!o.hasOwnProperty("raw"))throw Error("invalid template strings array");return Te!==void 0?Te.createHTML(e):e}var gt=(o,e)=>{let t=o.length-1,n=[],r,s=e===2?"<svg>":e===3?"<math>":"",i=V;for(let l=0;l<t;l++){let a=o[l],p,m,h=-1,g=0;for(;g<a.length&&(i.lastIndex=g,m=i.exec(a),m!==null);)g=i.lastIndex,i===V?m[1]==="!--"?i=Oe:m[1]!==void 0?i=De:m[2]!==void 0?(ze.test(m[2])&&(r=RegExp("</"+m[2],"g")),i=k):m[3]!==void 0&&(i=k):i===k?m[0]===">"?(i=r??V,h=-1):m[1]===void 0?h=-2:(h=i.lastIndex-m[2].length,p=m[1],i=m[3]===void 0?k:m[3]==='"'?Ue:Ie):i===Ue||i===Ie?i=k:i===Oe||i===De?i=V:(i=k,r=void 0);let x=i===k&&o[l+1].startsWith("/>")?" ":"";s+=i===V?a+ft:h>=0?(n.push(p),a.slice(0,h)+Ne+a.slice(h)+C+x):a+C+(h===-2?l:x)}return[Ke(o,s+(o[t]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),n]},K=class o{constructor({strings:e,_$litType$:t},n){let r;this.parts=[];let s=0,i=0,l=e.length-1,a=this.parts,[p,m]=gt(e,t);if(this.el=o.createElement(p,n),E.currentNode=this.el.content,t===2||t===3){let h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;(r=E.nextNode())!==null&&a.length<l;){if(r.nodeType===1){if(r.hasAttributes())for(let h of r.getAttributeNames())if(h.endsWith(Ne)){let g=m[i++],x=r.getAttribute(h).split(C),w=/([.?@])?(.*)/.exec(g);a.push({type:1,index:s,name:w[2],strings:x,ctor:w[1]==="."?ge:w[1]==="?"?ye:w[1]==="@"?be:H}),r.removeAttribute(h)}else h.startsWith(C)&&(a.push({type:6,index:s}),r.removeAttribute(h));if(ze.test(r.tagName)){let h=r.textContent.split(C),g=h.length-1;if(g>0){r.textContent=Q?Q.emptyScript:"";for(let x=0;x<g;x++)r.append(h[x],z()),E.nextNode(),a.push({type:2,index:++s});r.append(h[g],z())}}}else if(r.nodeType===8)if(r.data===Ve)a.push({type:2,index:s});else{let h=-1;for(;(h=r.data.indexOf(C,h+1))!==-1;)a.push({type:7,index:s}),h+=C.length-1}s++}}static createElement(e,t){let n=P.createElement("template");return n.innerHTML=e,n}};function L(o,e,t=o,n){if(e===M)return e;let r=n!==void 0?t._$Co?.[n]:t._$Cl,s=B(e)?void 0:e._$litDirective$;return r?.constructor!==s&&(r?._$AO?.(!1),s===void 0?r=void 0:(r=new s(o),r._$AT(o,t,n)),n!==void 0?(t._$Co??=[])[n]=r:t._$Cl=r),r!==void 0&&(e=L(o,r._$AS(o,e.values),r,n)),e}var _e=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:n}=this._$AD,r=(e?.creationScope??P).importNode(t,!0);E.currentNode=r;let s=E.nextNode(),i=0,l=0,a=n[0];for(;a!==void 0;){if(i===a.index){let p;a.type===2?p=new j(s,s.nextSibling,this,e):a.type===1?p=new a.ctor(s,a.name,a.strings,this,e):a.type===6&&(p=new ve(s,this,e)),this._$AV.push(p),a=n[++l]}i!==a?.index&&(s=E.nextNode(),i++)}return E.currentNode=P,r}p(e){let t=0;for(let n of this._$AV)n!==void 0&&(n.strings!==void 0?(n._$AI(e,n,t),t+=n.strings.length-2):n._$AI(e[t])),t++}},j=class o{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,n,r){this.type=2,this._$AH=u,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=n,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=L(this,e,t),B(e)?e===u||e==null||e===""?(this._$AH!==u&&this._$AR(),this._$AH=u):e!==this._$AH&&e!==M&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):_t(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==u&&B(this._$AH)?this._$AA.nextSibling.data=e:this.T(P.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:n}=e,r=typeof n=="number"?this._$AC(e):(n.el===void 0&&(n.el=K.createElement(Ke(n.h,n.h[0]),this.options)),n);if(this._$AH?._$AD===r)this._$AH.p(t);else{let s=new _e(r,this),i=s.u(this.options);s.p(t),this.T(i),this._$AH=s}}_$AC(e){let t=Fe.get(e.strings);return t===void 0&&Fe.set(e.strings,t=new K(e)),t}k(e){we(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,n,r=0;for(let s of e)r===t.length?t.push(n=new o(this.O(z()),this.O(z()),this,this.options)):n=t[r],n._$AI(s),r++;r<t.length&&(this._$AR(n&&n._$AB.nextSibling,r),t.length=r)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let n=He(e).nextSibling;He(e).remove(),e=n}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},H=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,n,r,s){this.type=1,this._$AH=u,this._$AN=void 0,this.element=e,this.name=t,this._$AM=r,this.options=s,n.length>2||n[0]!==""||n[1]!==""?(this._$AH=Array(n.length-1).fill(new String),this.strings=n):this._$AH=u}_$AI(e,t=this,n,r){let s=this.strings,i=!1;if(s===void 0)e=L(this,e,t,0),i=!B(e)||e!==this._$AH&&e!==M,i&&(this._$AH=e);else{let l=e,a,p;for(e=s[0],a=0;a<s.length-1;a++)p=L(this,l[n+a],t,a),p===M&&(p=this._$AH[a]),i||=!B(p)||p!==this._$AH[a],p===u?e=u:e!==u&&(e+=(p??"")+s[a+1]),this._$AH[a]=p}i&&!r&&this.j(e)}j(e){e===u?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},ge=class extends H{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===u?void 0:e}},ye=class extends H{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==u)}},be=class extends H{constructor(e,t,n,r,s){super(e,t,n,r,s),this.type=5}_$AI(e,t=this){if((e=L(this,e,t,0)??u)===M)return;let n=this._$AH,r=e===u&&n!==u||e.capture!==n.capture||e.once!==n.once||e.passive!==n.passive,s=e!==u&&(n===u||r);r&&this.element.removeEventListener(this.name,this,n),s&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},ve=class{constructor(e,t,n){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=n}get _$AU(){return this._$AM._$AU}_$AI(e){L(this,e)}};var yt=xe.litHtmlPolyfillSupport;yt?.(K,j),(xe.litHtmlVersions??=[]).push("3.3.3");var je=(o,e,t)=>{let n=t?.renderBefore??e,r=n._$litPart$;if(r===void 0){let s=t?.renderBefore??null;n._$litPart$=r=new j(e.insertBefore(z(),s),s,void 0,t??{})}return r._$AI(o),r};var Ce=globalThis,v=class extends ${constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=je(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return M}};v._$litElement$=!0,v.finalized=!0,Ce.litElementHydrateSupport?.({LitElement:v});var bt=Ce.litElementPolyfillSupport;bt?.({LitElement:v});(Ce.litElementVersions??=[]).push("4.2.2");function vt(o,e,t){return Math.min(Math.max(o,e),t)}function ee(o,e,t){return t<=e?.5:vt((o-e)/(t-e),0,1)}function xt(o,e,t){if(o==null)return"unknown";if(o<e)return"below";if(o>t)return"above";let n=t-e;if(n<=0)return"in_band";let r=(o-e)/n;return r<.25?"cool_edge":r>.75?"warm_edge":"in_band"}function qe(o){let{operative:e,setpoint:t,low:n,high:r}=o;if(n==null||r==null||r<=n)return null;let s=n-1.5,i=r+1.5;return{low:n,high:r,span:r-n,operative:e,setpoint:t,category:o.category??"",verdict:xt(e,n,r),axisLow:s,axisHigh:i,lowFrac:ee(n,s,i),highFrac:ee(r,s,i),operativeFrac:e==null?null:ee(e,s,i),setpointFrac:t==null?null:ee(t,s,i)}}var We={ok:"var(--success-color, #43a047)",warn:"var(--warning-color, #fb8c00)",alert:"var(--error-color, #e53935)",unknown:"var(--disabled-text-color, #9e9e9e)"};function q(o){return We[o]??We.unknown}var wt=[1e3,2e3],$t=[30,40,60,65],Ct=[26,30],At=420,St=[800,1350];function _(o){return typeof o=="number"&&Number.isFinite(o)}function te(o,e){return o&&o.length>=2&&_(o[0])&&_(o[1])&&o[0]<o[1]?[o[0],o[1]]:[e[0],e[1]]}function kt(o,e){if(o&&o.length>=4&&o.slice(0,4).every(_)){let[t,n,r,s]=o;if(t<=n&&n<=r&&r<=s)return[t,n,r,s]}return[e[0],e[1],e[2],e[3]]}function Et(o){if(o?.scheme==="en16798"){let e=_(o.outdoor)?o.outdoor:At,t=te(o.enRise,St);return[e+t[0],e+t[1]]}return te(o?.thresholds,wt)}function Pt(o,e){if(!_(o))return"unknown";let[t,n]=Et(e);return o>=n?"alert":o>=t?"warn":"ok"}function Mt(o,e){if(!_(o))return"unknown";let[t,n,r,s]=kt(e,$t);return o<t||o>=s?"alert":o<n||o>r?"warn":"ok"}function Rt(o){switch(o){case"in_band":return"ok";case"cool_edge":case"warm_edge":return"warn";case"below":case"above":return"alert";default:return"unknown"}}function Lt(o,e){if(!_(o))return"unknown";let[t,n]=te(e,Ct);return o>n?"alert":o>t?"warn":"ok"}var Ht=[10,15];function Tt(o){return 100-95*Math.exp(-(.03353*o**4+.2179*o**2))}function Ot(o,e,t){let[n,r]=te(t,Ht),s=_(e)?e:_(o)?Tt(o):null;return s==null?"unknown":s>=r?"alert":s>=n?"warn":"ok"}var Dt=[.5,1],It=[3,6],Ut=[85,60];function Xe(o){return o<=1?o*100:o}var Ge={unknown:-1,ok:0,warn:1,alert:2};function Ft(o){let e=[];if(_(o.deviationK)){let[t,n]=Dt;e.push(o.deviationK>=n?"alert":o.deviationK>=t?"warn":"ok")}if(_(o.cyclesPerH)){let[t,n]=It;e.push(o.cyclesPerH>=n?"alert":o.cyclesPerH>=t?"warn":"ok")}if(_(o.timeInBand)){let t=Xe(o.timeInBand),[n,r]=Ut;e.push(t<r?"alert":t<n?"warn":"ok")}return e.length?e.reduce((t,n)=>Ge[n]>Ge[t]?n:t,"ok"):"unknown"}function Ye(o,e){let t=[],n=e?.temperature_scale==="asr_office"?Lt(o.temperature,e.asr_thresholds):Rt(o.comfortVerdict??null);if(t.push({key:"temperature",value:o.temperature,unit:"\xB0C",level:n,color:q(n)}),_(o.humidity)){let s=Mt(o.humidity,e?.humidity_thresholds);t.push({key:"humidity",value:o.humidity,unit:"%",level:s,color:q(s)})}if(_(o.co2)){let s=Pt(o.co2,{scheme:e?.co2_scheme,thresholds:e?.co2_thresholds,outdoor:e?.outdoor_co2});t.push({key:"co2",value:o.co2,unit:"ppm",level:s,color:q(s)})}if(_(o.pmv)||_(o.ppd)){let s=Ot(o.pmv??null,o.ppd??null);t.push({key:"pmv",value:_(o.ppd)?o.ppd:null,unit:"%",level:s,color:q(s)})}let r=o.ca;if(r&&(_(r.deviationK)||_(r.timeInBand)||_(r.cyclesPerH))){let s=Ft(r);t.push({key:"ca",value:_(r.timeInBand)?Xe(r.timeInBand):null,unit:"%",level:s,color:q(s)})}return t}var Ae=["hvac","window","temperature","humidity","co2","ca"],Nt=[12,24,48];function Je(o,e,t){return typeof o=="string"&&e.includes(o)?o:t}function T(o,e){return typeof o=="boolean"?o:e}function Vt(o){return o===!1?new Set:o==null||o===!0?new Set(Ae):Array.isArray(o)?new Set(o.filter(e=>Ae.includes(e))):new Set(Ae)}function zt(o){if(o===!1)return{show:!1,hours:24};if(o===!0||o==null)return{show:!0,hours:24};let e=typeof o.hours=="number"?o.hours:Number(o.hours),t=Nt.includes(e)?e:24;return{show:T(o.show,!0),hours:t}}function Ze(o){let e=o.sections??{},t=o.density?Je(o.density,["comfortable","compact"],"comfortable"):o.compact?"compact":"comfortable";return{entity:o.entity,density:t,controls:Je(o.controls,["dial","buttons","none"],"dial"),history:zt(o.history),chips:Vt(e.chips),shadowPill:T(e.shadow_pill,T(o.show_shadow,!0)),learning:T(e.learning,!0),pmv:T(e.pmv,!0),presets:T(e.presets,!0),temperature_scale:o.temperature_scale,humidity_thresholds:o.humidity_thresholds,co2_scheme:o.co2_scheme,co2_thresholds:o.co2_thresholds}}var Qe={in_band:"In comfort band",cool_edge:"Cool edge of band",warm_edge:"Warm edge of band",below:"Below comfort band",above:"Above comfort band",unknown:"No reading",preheating:"Pre-heating",coasting:"Coasting",window:"Window open",window_auto:"Window (auto)",bypass:"Window detection off",eco:"Eco",comfort:"Comfort",boost:"Boost",away:"Away",failure:"Heating failure",learning:"Learning",shadow:"Shadow active",setpoint:"Setpoint",no_entity:"Select a Poise thermostat entity.",min_left:"min",no_system:"Select the Poise System sensor.",sys_title:"Poise System",demand_on:"Boiler demand",demand_off:"No demand",frost:"Frost override",zones:"zones",heating_n:"heating",flow:"Flow",shed:"shed",shadow_would:"would",update_msg:"New Poise card version available \u2014 reload to update.",reload:"Reload",details:"Show details",temperature:"Temperature",humidity:"Humidity",co2:"CO\u2082",pmv:"Comfort",ca:"Regulation",override_clamped:"Setpoint clamped",mould:"Mould limit",presets:"Presets",air_quality:"Room condition",air_ok:"OK",air_warn:"Elevated",air_alert:"Critical"},Bt={in_band:"Im Komfortband",cool_edge:"Untere Bandkante",warm_edge:"Obere Bandkante",below:"Unter dem Komfortband",above:"\xDCber dem Komfortband",unknown:"Kein Messwert",preheating:"Vorheizen",coasting:"Auslaufen",window:"Fenster offen",window_auto:"Fenster (auto)",bypass:"Fenster-Erkennung aus",eco:"Eco",comfort:"Komfort",boost:"Boost",away:"Abwesend",failure:"Heizausfall",learning:"Lernt",shadow:"Shadow aktiv",setpoint:"Sollwert",no_entity:"Bitte eine Poise-Thermostat-Entit\xE4t w\xE4hlen.",min_left:"Min",no_system:"Bitte den Poise-System-Sensor w\xE4hlen.",sys_title:"Poise System",demand_on:"Kesselbedarf",demand_off:"Kein Bedarf",frost:"Frost-Override",zones:"Zonen",heating_n:"heizen",flow:"Vorlauf",shed:"abgeworfen",shadow_would:"w\xFCrde",update_msg:"Neue Poise-Karten-Version verf\xFCgbar \u2014 zum Aktualisieren neu laden.",reload:"Neu laden",details:"Details anzeigen",temperature:"Temperatur",humidity:"Feuchte",co2:"CO\u2082",pmv:"Behaglichkeit",ca:"Regelg\xFCte",override_clamped:"Sollwert geklemmt",mould:"Schimmelgrenze",presets:"Voreinstellungen",air_quality:"Raumzustand",air_ok:"OK",air_warn:"Erh\xF6ht",air_alert:"Kritisch"};function d(o,e){return((o??"en").toLowerCase().startsWith("de")?Bt:Qe)[e]??Qe[e]??e}var Kt=[{value:"hvac",label:"HVAC status"},{value:"window",label:"Window"},{value:"temperature",label:"Temperature"},{value:"humidity",label:"Humidity"},{value:"co2",label:"CO\u2082"},{value:"ca",label:"Regulation (CA)"}],jt=[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"climate"}}},{name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}},{name:"controls",selector:{select:{mode:"dropdown",options:[{value:"dial",label:"Dial (drag)"},{value:"buttons",label:"Buttons (+/\u2212)"},{value:"none",label:"Display only"}]}}},{type:"expandable",name:"history",title:"History",schema:[{name:"show",selector:{boolean:{}}},{name:"hours",selector:{select:{mode:"dropdown",options:[{value:12,label:"12 h"},{value:24,label:"24 h"},{value:48,label:"48 h"}]}}}]},{type:"expandable",name:"sections",title:"Sections",schema:[{name:"chips",selector:{select:{multiple:!0,options:Kt}}},{name:"pmv",selector:{boolean:{}}},{name:"presets",selector:{boolean:{}}},{name:"shadow_pill",selector:{boolean:{}}},{name:"learning",selector:{boolean:{}}}]},{type:"expandable",name:"",title:"Advanced",flatten:!0,schema:[{name:"temperature_scale",selector:{select:{mode:"dropdown",options:[{value:"comfort",label:"Comfort band"},{value:"asr_office",label:"ASR office (\u226426 \xB0C)"}]}}},{name:"co2_scheme",selector:{select:{mode:"dropdown",options:[{value:"uba",label:"UBA (absolute)"},{value:"en16798",label:"EN 16798 (outdoor offset)"}]}}}]}],qt={entity:"Entity",density:"Density",controls:"Controls",history:"History",sections:"Sections",show:"Show graph",hours:"Time span",chips:"Condition chips",pmv:"Comfort (PMV) lamp",presets:"Preset buttons",shadow_pill:"Shadow pill",learning:"Learning bar",temperature_scale:"Temperature scale",co2_scheme:"CO\u2082 scale"},ne=class extends v{setConfig(e){this._config=e}shouldUpdate(e){return e.has("hass")||e.has("_config")}_changed(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e.detail.value}}))}render(){return!this.hass||!this._config?f``:f`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${jt}
      .computeLabel=${e=>qt[e.name]??e.name}
      @value-changed=${this._changed}
    ></ha-form>`}};ne.properties={hass:{},_config:{state:!0}};customElements.get("poise-card-editor")||customElements.define("poise-card-editor",ne);var oe="0.141.0",et=!1;function Wt(){let o=()=>location.reload();"caches"in window?caches.keys().then(e=>Promise.all(e.map(t=>caches.delete(t)))).then(o,o):o()}async function re(o,e){if(!(et||!e?.connection)){et=!0;try{let t=await e.connection.sendMessagePromise({type:"poise/card_version"});if(t?.version&&t.version!==oe){let n=e.locale?.language;o.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:`${d(n,"update_msg")} (${oe} \u2192 ${t.version})`,duration:-1,dismissable:!0,action:{text:d(n,"reload"),action:Wt}},bubbles:!0,composed:!0}))}}catch{}}}function W(o){let e=typeof o=="string"?parseFloat(o):o;return typeof e=="number"&&!Number.isNaN(e)?e:null}var G=class extends v{static getConfigElement(){return document.createElement("poise-system-card-editor")}static getStubConfig(e){return{type:"custom:poise-system-card",entity:Object.keys(e.states).find(n=>n.startsWith("binary_sensor.")&&e.states[n].attributes.zone_count!==void 0)??""}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config=e}getCardSize(){return 2}getGridOptions(){return{columns:12,rows:"auto",min_columns:4,min_rows:4}}updated(){this.hass&&re(this,this.hass)}shouldUpdate(e){if(e.has("_config"))return!0;let t=e.get("hass");return!t||!this._config?.entity?!0:t.states[this._config.entity]!==this.hass.states[this._config.entity]}_moreInfo(){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_onActivateKey(e){(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),this._moreInfo())}render(){let e=this.hass?.locale?.language,t=this._config?.entity,n=t?this.hass.states[t]:void 0;if(!n)return f`<ha-card
        ><div class="empty">${d(e,"no_system")}</div></ha-card
      >`;let r=n.attributes,s=n.state==="on",i=W(r.flow_target),l=W(r.shed_count)??0,a=r.source_grants??{},p=Object.keys(a);return f`<ha-card .header=${d(e,"sys_title")}>
      <div
        class="wrap"
        role="button"
        tabindex="0"
        aria-label=${d(e,"details")}
        @click=${this._moreInfo}
        @keydown=${this._onActivateKey}
      >
        <div class="state ${s?"on":""}">
          <ha-icon icon=${s?"mdi:fire":"mdi:fire-off"}></ha-icon>
          <span>${s?d(e,"demand_on"):d(e,"demand_off")}</span>
          ${r.frost_override?f`<em class="frost">${d(e,"frost")}</em>`:u}
        </div>
        <div class="stats">
          <div>
            <strong>${W(r.active_zones)??0}</strong
            ><span>${d(e,"heating_n")}</span>
          </div>
          <div>
            <strong
              >${W(r.controlling_zones)??0}/${W(r.zone_count)??0}</strong
            ><span>${d(e,"zones")}</span>
          </div>
          ${i!=null?f`<div>
                <strong>${i.toFixed(0)}°</strong><span>${d(e,"flow")}</span>
              </div>`:u}
          ${l>0?f`<div>
                <strong>${l}</strong><span>${d(e,"shed")}</span>
              </div>`:u}
        </div>
        ${p.length?f`<div class="grants">
              ${p.map(m=>f`<span class="chip">${m}: ${a[m]}</span>`)}
            </div>`:u}
      </div>
    </ha-card>`}};G.properties={hass:{},_config:{state:!0}},G.styles=F`
    .wrap { padding: 8px 16px 16px; cursor: pointer; }
    .wrap:focus { outline: none; }
    .wrap:focus-visible {
      outline: 2px solid var(--primary-color, #2196f3);
      outline-offset: -2px; border-radius: 10px;
    }
    .state { display: flex; align-items: center; gap: 8px; font-size: 18px; }
    .state ha-icon { --mdc-icon-size: 22px; color: var(--secondary-text-color); }
    .state.on ha-icon { color: var(--error-color, #d33); }
    .frost { font-style: normal; margin-left: auto; padding: 2px 8px; border-radius: 10px;
      font-size: 11px; background: var(--info-color, #2196f3); color: var(--text-primary-color, #fff); }
    .stats { display: flex; gap: 18px; margin-top: 10px; flex-wrap: wrap; }
    .stats strong { font-size: 20px; }
    .stats span { display: block; font-size: 11px; color: var(--secondary-text-color); }
    .grants { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .chip { padding: 3px 8px; border-radius: 12px; font-size: 12px;
      background: var(--secondary-background-color); }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;var se=class extends v{setConfig(e){this._config=e}shouldUpdate(e){return e.has("hass")||e.has("_config")}_changed(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e.detail.value}}))}render(){return!this.hass||!this._config?f``:f`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"binary_sensor"}}}]}
      .computeLabel=${e=>e.name}
      @value-changed=${this._changed}
    ></ha-form>`}};se.properties={hass:{},_config:{state:!0}};customElements.get("poise-system-card-editor")||customElements.define("poise-system-card-editor",se);customElements.get("poise-system-card")||customElements.define("poise-system-card",G);window.customCards=window.customCards||[];window.customCards.push({type:"poise-system-card",name:"Poise System",preview:!0,description:"Multi-zone boiler demand, flow & load shedding for the Poise hub."});function tt(o,e,t){return Math.min(Math.max(o,e),t)}function nt(o,e,t,n=300,r=90,s=1){let i=[];for(let y of o)y.op!=null&&i.push(y.op),y.sp!=null&&i.push(y.sp);if(e!=null&&i.push(e),t!=null&&i.push(t),i.length===0||o.length===0)return null;let l=Math.min(...i)-s,a=Math.max(...i)+s,p=o[0].t,h=o[o.length-1].t-p||1,g=a-l||1,x=y=>(y-p)/h*n,w=y=>r-(y-l)/g*r,D=y=>o.filter(S=>y(S)!=null).map(S=>`${x(S.t).toFixed(1)},${w(y(S)).toFixed(1)}`).join(" ");return{width:n,height:r,opPath:D(y=>y.op),spPath:D(y=>y.sp),bandTop:t==null?0:tt(w(t),0,r),bandBottom:e==null?r:tt(w(e),0,r),vMin:l,vMax:a}}var b={min:16,max:28,start:135,sweep:270};function ot(o,e,t){return Math.min(Math.max(o,e),t)}function O(o,e=b){let t=ot((o-e.min)/(e.max-e.min),0,1);return e.start+t*e.sweep}function Gt(o,e=b){let t=o;for(;t<e.start;)t+=360;for(;t>=e.start+360;)t-=360;if(t<=e.start+e.sweep)return t;let n=t-(e.start+e.sweep);return e.start+360-t<n?e.start:e.start+e.sweep}function Xt(o,e=b){let n=(Gt(o,e)-e.start)/e.sweep;return e.min+n*(e.max-e.min)}function A(o,e,t,n){let r=n*Math.PI/180;return{x:o+t*Math.cos(r),y:e+t*Math.sin(r)}}function Se(o,e,t,n,r){if(r<=n)return"";let s=A(o,e,t,n),i=A(o,e,t,r),l=r-n>180?1:0;return`M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${t} ${t} 0 ${l} 1 ${i.x.toFixed(2)} ${i.y.toFixed(2)}`}function rt(o,e,t=b){let n=Math.atan2(e,o)*180/Math.PI;return n<0&&(n+=360),Xt(n,t)}function st(o,e,t,n=b){let r;switch(o){case"ArrowUp":case"ArrowRight":r=e+t;break;case"ArrowDown":case"ArrowLeft":r=e-t;break;case"PageUp":r=e+t*5;break;case"PageDown":r=e-t*5;break;case"Home":r=n.min;break;case"End":r=n.max;break;default:return null}return Math.round(ot(r,n.min,n.max)/t)*t}function it(o){return{eco:"mdi:leaf",boost:"mdi:rocket-launch",away:"mdi:home-export-outline",comfort:"mdi:sofa"}[o]??"mdi:tune"}function c(o){let e=typeof o=="string"?parseFloat(o):o;return typeof e=="number"&&!Number.isNaN(e)?e:null}var X=class extends v{constructor(){super(...arguments);this._history=[];this._histFor=null;this._dragging=!1;this._pending=null;this._dialCfg=b}static getConfigElement(){return document.createElement("poise-card-editor")}static getStubConfig(t){return{type:"custom:poise-card",entity:Object.keys(t.states).find(r=>r.startsWith("climate.")&&t.states[r].attributes.comfort_low!==void 0)??"",show_shadow:!0}}setConfig(t){if(!t)throw new Error("Invalid configuration");if(t.entity&&!t.entity.startsWith("climate."))throw new Error("Poise card: entity must be a climate entity");this._config={show_shadow:!0,...t},this._r=Ze(this._config)}getCardSize(){return 4}getGridOptions(){return this._r?.density==="compact"?{columns:6,rows:"auto",min_columns:4,min_rows:6}:{columns:12,rows:"auto",min_columns:6,min_rows:9}}shouldUpdate(t){if(this._dragging||t.has("_config"))return!0;let n=t.get("hass");return!n||!this._config?.entity?!0:n.states[this._config.entity]!==this.hass.states[this._config.entity]}_setpoint(t){let n=this._config.entity;if(!n||!this.hass)return;let r=this.hass.states[n];if(!r)return;let s=c(r.attributes.target_temperature_step)??.5,i=c(r.attributes.heat_sp)??c(r.attributes.temperature)??21;this.hass.callService("climate","set_temperature",{entity_id:n,temperature:Math.round((i+t*s)*10)/10})}updated(){this.hass&&re(this,this.hass);let t=this._config?.entity;t&&this.hass&&this._r?.history.show&&this._histFor!==t&&(this._histFor=t,this._loadHistory(t))}async _loadHistory(t){if(!this.hass.connection)return;let n=this._r?.history.hours??24,r=new Date,s=new Date(r.getTime()-n*3600*1e3);try{let l=(await this.hass.connection.sendMessagePromise({type:"history/history_during_period",start_time:s.toISOString(),end_time:r.toISOString(),entity_ids:[t],minimal_response:!1,no_attributes:!1}))?.[t]??[],a={},p=[];for(let m of l){m.a&&(a={...a,...m.a});let h=(c(m.lu)??c(m.lc)??0)*1e3;p.push({t:h,op:c(a.operative_temperature)??c(a.current_temperature),sp:c(a.heat_sp)??c(a.temperature)})}this._history=p,this.requestUpdate()}catch{}}_moreInfo(){this._config.entity&&this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_chart(t,n){let r=nt(this._history,t,n,300,80);return r?f`<svg
      class="chart"
      viewBox="0 0 ${r.width} ${r.height}"
      preserveAspectRatio="none"
    >
      <rect
        x="0"
        y=${r.bandTop}
        width=${r.width}
        height=${Math.max(0,r.bandBottom-r.bandTop)}
        class="cband"
      ></rect>
      <polyline points=${r.spPath} class="csp"></polyline>
      <polyline points=${r.opPath} class="cop"></polyline>
    </svg>`:u}render(){let t=this.hass?.locale?.language,n=this._config?.entity,r=n?this.hass.states[n]:void 0;if(!r)return f`<ha-card
        ><div class="empty">${d(t,"no_entity")}</div></ha-card
      >`;let s=r.attributes,i=c(s.operative_temperature)??c(s.current_temperature),l=c(s.heat_sp)??c(s.temperature),a=qe({operative:i,setpoint:l,low:c(s.comfort_low),high:c(s.comfort_high),category:s.category??null}),p=this._r;return f`<ha-card .header=${s.friendly_name??"Poise"}>
      <div class="wrap ${p.density==="compact"?"compact":""}">
        ${this._dial(s,t)}
        <div class="verdict">
          ${a?d(t,a.verdict):d(t,"unknown")}
          ${a?.category?f`<span class="cat">Kat. ${a.category}</span>`:u}
        </div>
        ${p.controls==="buttons"?this._control(this._pending??l,t):u}
        ${this._presets(s,t)}
        ${p.history.show?this._chart(c(s.comfort_low),c(s.comfort_high)):u}
        ${this._monitor(s,a,t)} ${this._chips(s,t)}
        ${this._learn(s,t)}
      </div>
    </ha-card>`}_dial(t,n){let r=c(t.operative_temperature)??c(t.current_temperature),s=c(t.heat_sp)??c(t.temperature),i={min:c(t.min_temp)??b.min,max:c(t.max_temp)??b.max,start:b.start,sweep:b.sweep};this._dialCfg=i.max>i.min?i:b;let l=this._pending??s??r??this._dialCfg.min,a=c(t.comfort_low),p=c(t.comfort_high),m=100,h=100,g=80,x=Se(m,h,g,b.start,b.start+b.sweep),w=a!=null&&p!=null?Se(m,h,g,O(Math.min(a,p),this._dialCfg),O(Math.max(a,p),this._dialCfg)):"",D=String(t.hvac_action??""),y=D==="heating"?"heat":D==="cooling"?"cool":"",S=A(m,h,g,O(l,this._dialCfg)),ie=r!=null?A(m,h,g,O(r,this._dialCfg)):null,R=c(t.mould_floor),I=R!=null&&R>this._dialCfg.min&&R<this._dialCfg.max,ae=I?O(R,this._dialCfg):0,le=I?A(m,h,g-9,ae):null,ce=I?A(m,h,g+9,ae):null,de=I?A(m,h,g+17,ae):null,pe=this._r.controls==="dial";return f`<div class="dialwrap">
      <svg
        class="dial ${pe?"":"ro"}"
        viewBox="0 0 200 200"
        role=${pe?"slider":"img"}
        tabindex=${pe?0:-1}
        aria-label=${d(n,"setpoint")}
        aria-valuemin=${this._dialCfg.min}
        aria-valuemax=${this._dialCfg.max}
        aria-valuenow=${l}
        aria-valuetext="${l.toFixed(1)} °C"
        @keydown=${this._onKey}
        @pointerdown=${this._onDown}
        @pointermove=${this._onMove}
        @pointerup=${this._onUp}
        @pointercancel=${this._onUp}
      >
        <path class="track" d=${x}></path>
        <path class="bandarc" d=${w}></path>
        ${I&&le&&ce&&de?Be`<line class="mould" x1=${le.x.toFixed(1)} y1=${le.y.toFixed(1)} x2=${ce.x.toFixed(1)} y2=${ce.y.toFixed(1)}><title>${d(n,"mould")} ${R.toFixed(1)}°</title></line><text class="mlbl" x=${de.x.toFixed(1)} y=${de.y.toFixed(1)}>${R.toFixed(0)}°</text>`:u}
        <circle
          class="opdot"
          cx=${(ie?.x??0).toFixed(1)}
          cy=${(ie?.y??0).toFixed(1)}
          r=${ie?5:0}
        ></circle>
        <circle class="handle ${y}" cx=${S.x.toFixed(1)} cy=${S.y.toFixed(1)} r="9"></circle>
      </svg>
      <div class="dialctr">
        <div
          class="ctrclick"
          role="button"
          tabindex="0"
          aria-label=${d(n,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          <div class="op">${r!=null?r.toFixed(1):"\u2014"}<span>°C</span></div>
          <div class="soll">${d(n,"setpoint")} <b>${l.toFixed(1)}°</b></div>
        </div>
      </div>
    </div>`}_fromPointer(t,n){let r=n.getBoundingClientRect();if(!r.width||!this._config.entity)return;let s=(t.clientX-r.left)/r.width*200-100,i=(t.clientY-r.top)/r.height*200-100,l=c(this.hass.states[this._config.entity]?.attributes.target_temperature_step)??.5;this._pending=Math.round(rt(s,i,this._dialCfg)/l)*l,this.requestUpdate()}_onDown(t){if(!this._config.entity||this._r.controls!=="dial")return;t.preventDefault();let n=t.currentTarget;n.setPointerCapture(t.pointerId),this._dragging=!0,this._fromPointer(t,n)}_onMove(t){this._dragging&&this._fromPointer(t,t.currentTarget)}_onUp(){if(!this._dragging)return;this._dragging=!1;let t=this._pending;this._pending=null,t!=null&&this._config.entity&&this.hass.callService("climate","set_temperature",{entity_id:this._config.entity,temperature:t}),this.requestUpdate()}_onKey(t){let n=this._config.entity;if(!n||this._r.controls!=="dial")return;let r=this.hass.states[n];if(!r)return;let s=c(r.attributes.target_temperature_step)??.5,i=c(r.attributes.heat_sp)??c(r.attributes.temperature)??this._dialCfg.min,l=st(t.key,i,s,this._dialCfg);l!=null&&(t.preventDefault(),this.hass.callService("climate","set_temperature",{entity_id:n,temperature:l}))}_onActivateKey(t){(t.key==="Enter"||t.key===" ")&&(t.preventDefault(),this._moreInfo())}_control(t,n){return f`<div class="ctl">
      <ha-icon-button @click=${()=>this._setpoint(-1)} label="-">
        <ha-icon icon="mdi:minus"></ha-icon>
      </ha-icon-button>
      <div class="sp">
        <span>${d(n,"setpoint")}</span
        ><strong>${t!=null?t.toFixed(1):"\u2014"}°C</strong>
      </div>
      <ha-icon-button @click=${()=>this._setpoint(1)} label="+">
        <ha-icon icon="mdi:plus"></ha-icon>
      </ha-icon-button>
    </div>`}_setPreset(t){let n=this._config.entity;!n||!this.hass||this.hass.callService("climate","set_preset_mode",{entity_id:n,preset_mode:t})}_presets(t,n){if(!this._r.presets)return u;let r=t.preset_modes;if(!Array.isArray(r)||!r.length)return u;let s=t.preset_mode==null?null:String(t.preset_mode);return f`<div class="presets" role="group" aria-label=${d(n,"presets")}>
      ${r.map(i=>{let l=String(i);return f`<button
          class="preset ${s===l?"on":""}"
          aria-pressed=${s===l?"true":"false"}
          @click=${()=>this._setPreset(l)}
        >
          <ha-icon icon=${it(l.toLowerCase())}></ha-icon>
          <span>${d(n,l.toLowerCase())||l}</span>
        </button>`})}
    </div>`}_chips(t,n){let r=this._r,s=[];if(r.chips.has("hvac")){t.preheating&&s.push(this._chip("mdi:fire-circle",d(n,"preheating"),t.minutes_to_comfort,n)),t.coasting&&s.push(this._chip("mdi:coffee",d(n,"coasting"),t.minutes_to_setback,n));let i=t.preset==null?"none":String(t.preset);i!=="none"&&!r.presets&&s.push(this._chip(it(i),d(n,i)||i)),t.heating_failure&&s.push(this._chip("mdi:alert",d(n,"failure"))),t.override_clamped&&s.push(this._chip("mdi:arrow-collapse-vertical",d(n,"override_clamped")));let l=t.binding_lower_cause;l&&l!=="en16798"&&s.push(this._chip("mdi:shield-alert",String(l)))}return r.chips.has("window")&&(t.window_open&&s.push(this._chip("mdi:window-open",d(n,t.window_auto_detected?"window_auto":"window"))),t.window_bypass&&s.push(this._chip("mdi:window-closed-variant",d(n,"bypass")))),s.length?f`<div
          class="chips"
          role="button"
          tabindex="0"
          aria-label=${d(n,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          ${s}
        </div>`:u}_chip(t,n,r,s){let i=c(r);return f`<div class="chip">
      <ha-icon icon=${t}></ha-icon><span>${n}</span>
      ${i!=null?f`<em>${Math.round(i)} ${d(s,"min_left")}</em>`:u}
    </div>`}_monitor(t,n,r){let s=Ye({temperature:c(t.operative_temperature)??c(t.current_temperature),comfortVerdict:n?.verdict??null,humidity:c(t.humidity)??c(t.current_humidity),co2:c(t.co2)??c(t.carbon_dioxide),pmv:c(t.pmv),ppd:c(t.ppd),ca:{deviationK:c(t.ca_deviation_k),timeInBand:c(t.ca_time_in_band),cyclesPerH:c(t.ca_cycles_per_h)}},{temperature_scale:this._config.temperature_scale,humidity_thresholds:this._config.humidity_thresholds,co2_scheme:this._config.co2_scheme,co2_thresholds:this._config.co2_thresholds,outdoor_co2:c(t.outdoor_co2)}),i=this._r,l=s.filter(a=>a.key==="pmv"?i.pmv:i.chips.has(a.key));return l.length?f`<div
      class="monitor"
      role="group"
      aria-label=${d(r,"air_quality")}
    >
      ${l.map(a=>this._lamp(a,r))}
    </div>`:u}_lamp(t,n){let r=d(n,t.key),s=d(n,t.level==="unknown"?"unknown":"air_"+t.level),i="\u2014";t.value!=null&&(i=t.key==="temperature"?t.value.toFixed(1):String(Math.round(t.value)));let l=`${r}: ${i} ${t.unit} \u2014 ${s}`;return f`<div class="lamp" title=${l} aria-label=${l}>
      <span class="dot" style="background:${t.color}"></span>
      <span class="lk">${r}</span>
      <span class="lv">${i}<small>${t.unit}</small></span>
    </div>`}_learn(t,n){let r=c(t.confidence),s=this._r.learning&&r!=null,i=this._r.shadowPill&&(t.mpc_active||t.tpi_active||t.pi_active);if(!s&&!i)return u;let l=c(t.pi_setpoint),a=c(t.mpc_setpoint),p=t.tpi_active?`TPI ${Math.round(c(t.tpi_valve_percent)??0)}%`:t.pi_active&&l!=null?`PI ${l.toFixed(1)}\xB0`:t.mpc_active&&a!=null?`MPC ${a.toFixed(1)}\xB0`:"";return f`<div class="learn">
      ${s?f`<div class="bar">
            <i style="width:${((r??0)*100).toFixed(0)}%"></i>
          </div>
          <span>${d(n,"learning")} ${((r??0)*100).toFixed(0)}%</span>`:u}
      ${i?f`<div class="pill">
            ${d(n,"shadow")}${p?f` · ${p}`:u}
          </div>`:u}
    </div>`}};X.properties={hass:{},_config:{state:!0}},X.styles=F`
    .wrap { padding: 8px 16px 16px; }
    .band {
      position: relative; height: 26px; margin: 8px 0 22px;
      border-radius: 13px; background: var(--divider-color, #e0e0e0);
    }
    .fill {
      position: absolute; top: 0; bottom: 0; border-radius: 13px;
      background: color-mix(in srgb, var(--success-color, #4caf50) 35%, transparent);
    }
    .mark { position: absolute; top: -3px; width: 4px; height: 32px; border-radius: 2px; transform: translateX(-2px); }
    .mark.op { background: var(--primary-color, #2196f3); }
    .mark.sp { background: var(--secondary-text-color, #888); }
    .tick { position: absolute; top: 28px; font-size: 11px; color: var(--secondary-text-color); transform: translateX(-50%); }
    .big { font-size: 40px; font-weight: 600; line-height: 1; }
    .big span { font-size: 18px; color: var(--secondary-text-color); }
    .verdict { color: var(--secondary-text-color); margin-bottom: 8px; }
    .cat { margin-left: 8px; opacity: 0.8; }
    .ctl { display: flex; align-items: center; justify-content: center; gap: 18px; margin: 10px 0 4px; }
    .sp { text-align: center; }
    .sp span { display: block; font-size: 12px; color: var(--secondary-text-color); }
    .sp strong { font-size: 20px; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    .chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .chip ha-icon { --mdc-icon-size: 16px; }
    .chip em { font-style: normal; color: var(--secondary-text-color); }
    .learn { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
    .bar { flex: 1; height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
    .bar i { display: block; height: 100%; background: var(--primary-color); }
    .learn span { font-size: 12px; color: var(--secondary-text-color); }
    .pill { padding: 2px 8px; border-radius: 10px; font-size: 11px;
      background: var(--primary-color); color: var(--text-primary-color, #fff); }
    .chart { width: 100%; height: 80px; margin: 10px 0 2px; display: block; }
    .cband { fill: color-mix(in srgb, var(--success-color, #4caf50) 16%, transparent); }
    .cop { fill: none; stroke: var(--primary-color, #2196f3); stroke-width: 2; vector-effect: non-scaling-stroke; }
    .csp { fill: none; stroke: var(--secondary-text-color, #888); stroke-width: 1.5; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
    .chips { cursor: pointer; }
    .monitor { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 2px; }
    .lamp { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .lamp .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
    .lamp .lk { color: var(--secondary-text-color); }
    .lamp .lv { font-weight: 600; }
    .lamp .lv small { font-weight: 400; color: var(--secondary-text-color); margin-left: 1px; }
    .dialwrap { position: relative; width: 100%; max-width: 230px; margin: 6px auto 2px; }
    .dial:focus, .ctrclick:focus, .chips:focus { outline: none; }
    .dial:focus-visible, .ctrclick:focus-visible, .chips:focus-visible {
      outline: 2px solid var(--primary-color, #2196f3);
      outline-offset: 2px; border-radius: 10px;
    }
    .dial { width: 100%; display: block; touch-action: none; cursor: pointer; }
    .track { fill: none; stroke: var(--divider-color, #444); stroke-width: 10; stroke-linecap: round; }
    .bandarc { fill: none; stroke: color-mix(in srgb, var(--success-color, #4caf50) 55%, transparent); stroke-width: 10; stroke-linecap: round; }
    .opdot { fill: var(--primary-text-color, #fff); }
    .handle { fill: var(--primary-color, #2196f3); stroke: var(--card-background-color, #1c1c1c); stroke-width: 2; }
    .dialctr { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; }
    .ctrclick { pointer-events: auto; cursor: pointer; display: flex; flex-direction: column; align-items: center; }
    .handle.heat { fill: var(--state-climate-heat-color, #ff8100); }
    .handle.cool { fill: var(--state-climate-cool-color, #2b9af9); }
    .wrap.compact .dialwrap { max-width: 150px; }
    .dialctr .op { font-size: 38px; font-weight: 600; line-height: 1; }
    .dialctr .op span { font-size: 16px; color: var(--secondary-text-color); }
    .dialctr .soll { font-size: 13px; color: var(--secondary-text-color); margin-top: 4px; }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
    .mould { stroke: var(--warning-color, #ff9800); stroke-width: 3; stroke-linecap: round; }
    .mlbl { fill: var(--warning-color, #ff9800); font-size: 11px; font-weight: 600;
      text-anchor: middle; dominant-baseline: middle; }
    .dial.ro { cursor: default; }
    .presets { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 2px; }
    .preset { display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px;
      border: 1px solid var(--divider-color, #e0e0e0); border-radius: 16px;
      background: var(--card-background-color, transparent);
      color: var(--primary-text-color); font: inherit; font-size: 13px; cursor: pointer; }
    .preset ha-icon { --mdc-icon-size: 16px; }
    .preset.on { background: var(--primary-color, #2196f3);
      color: var(--text-primary-color, #fff); border-color: var(--primary-color, #2196f3); }
    .preset:focus-visible { outline: 2px solid var(--primary-color, #2196f3); outline-offset: 2px; }
    .wrap.compact { padding: 6px 12px 12px; }
    .wrap.compact .dialctr .op { font-size: 30px; }
    .wrap.compact .presets, .wrap.compact .monitor, .wrap.compact .chips { gap: 4px; }
  `;window.customCards=window.customCards||[];window.customCards.push({type:"poise-card",name:"Poise Thermostat",preview:!0,description:"EN-16798 comfort band, operative temperature & shadow state for Poise."});customElements.get("poise-card")||customElements.define("poise-card",X);console.info(`%c POISE-CARD ${oe} `,"background:#2196f3;color:#fff");export{X as PoiseCard};
