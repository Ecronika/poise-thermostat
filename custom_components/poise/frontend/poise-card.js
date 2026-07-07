/* poise-card 0.154.0 — bundled, served by the Poise integration (ADR-0040) */
var Y=globalThis,J=Y.ShadowRoot&&(Y.ShadyCSS===void 0||Y.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,ue=Symbol(),ke=new WeakMap,U=class{constructor(e,t,o){if(this._$cssResult$=!0,o!==ue)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,t=this.t;if(J&&e===void 0){let o=t!==void 0&&t.length===1;o&&(e=ke.get(t)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),o&&ke.set(t,e))}return e}toString(){return this.cssText}},Ee=n=>new U(typeof n=="string"?n:n+"",void 0,ue),F=(n,...e)=>{let t=n.length===1?n[0]:e.reduce((o,r,s)=>o+(i=>{if(i._$cssResult$===!0)return i.cssText;if(typeof i=="number")return i;throw Error("Value passed to 'css' function must be a 'css' function result: "+i+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(r)+n[s+1],n[0]);return new U(t,n,ue)},Pe=(n,e)=>{if(J)n.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of e){let o=document.createElement("style"),r=Y.litNonce;r!==void 0&&o.setAttribute("nonce",r),o.textContent=t.cssText,n.appendChild(o)}},he=J?n=>n:n=>n instanceof CSSStyleSheet?(e=>{let t="";for(let o of e.cssRules)t+=o.cssText;return Ee(t)})(n):n;var{is:at,defineProperty:lt,getOwnPropertyDescriptor:ct,getOwnPropertyNames:dt,getOwnPropertySymbols:pt,getPrototypeOf:ut}=Object,Z=globalThis,Me=Z.trustedTypes,ht=Me?Me.emptyScript:"",mt=Z.reactiveElementPolyfillSupport,N=(n,e)=>n,me={toAttribute(n,e){switch(e){case Boolean:n=n?ht:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,e){let t=n;switch(e){case Boolean:t=n!==null;break;case Number:t=n===null?null:Number(n);break;case Object:case Array:try{t=JSON.parse(n)}catch{t=null}}return t}},Le=(n,e)=>!at(n,e),Re={attribute:!0,type:String,converter:me,reflect:!1,useDefault:!1,hasChanged:Le};Symbol.metadata??=Symbol("metadata"),Z.litPropertyMetadata??=new WeakMap;var w=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=Re){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let o=Symbol(),r=this.getPropertyDescriptor(e,o,t);r!==void 0&&lt(this.prototype,e,r)}}static getPropertyDescriptor(e,t,o){let{get:r,set:s}=ct(this.prototype,e)??{get(){return this[t]},set(i){this[t]=i}};return{get:r,set(i){let l=r?.call(this);s?.call(this,i),this.requestUpdate(e,l,o)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??Re}static _$Ei(){if(this.hasOwnProperty(N("elementProperties")))return;let e=ut(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(N("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(N("properties"))){let t=this.properties,o=[...dt(t),...pt(t)];for(let r of o)this.createProperty(r,t[r])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[o,r]of t)this.elementProperties.set(o,r)}this._$Eh=new Map;for(let[t,o]of this.elementProperties){let r=this._$Eu(t,o);r!==void 0&&this._$Eh.set(r,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let o=new Set(e.flat(1/0).reverse());for(let r of o)t.unshift(he(r))}else e!==void 0&&t.push(he(e));return t}static _$Eu(e,t){let o=t.attribute;return o===!1?void 0:typeof o=="string"?o:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let o of t.keys())this.hasOwnProperty(o)&&(e.set(o,this[o]),delete this[o]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Pe(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,o){this._$AK(e,o)}_$ET(e,t){let o=this.constructor.elementProperties.get(e),r=this.constructor._$Eu(e,o);if(r!==void 0&&o.reflect===!0){let s=(o.converter?.toAttribute!==void 0?o.converter:me).toAttribute(t,o.type);this._$Em=e,s==null?this.removeAttribute(r):this.setAttribute(r,s),this._$Em=null}}_$AK(e,t){let o=this.constructor,r=o._$Eh.get(e);if(r!==void 0&&this._$Em!==r){let s=o.getPropertyOptions(r),i=typeof s.converter=="function"?{fromAttribute:s.converter}:s.converter?.fromAttribute!==void 0?s.converter:me;this._$Em=r;let l=i.fromAttribute(t,s.type);this[r]=l??this._$Ej?.get(r)??l,this._$Em=null}}requestUpdate(e,t,o,r=!1,s){if(e!==void 0){let i=this.constructor;if(r===!1&&(s=this[e]),o??=i.getPropertyOptions(e),!((o.hasChanged??Le)(s,t)||o.useDefault&&o.reflect&&s===this._$Ej?.get(e)&&!this.hasAttribute(i._$Eu(e,o))))return;this.C(e,t,o)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,t,{useDefault:o,reflect:r,wrapped:s},i){o&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,i??t??this[e]),s!==!0||i!==void 0)||(this._$AL.has(e)||(this.hasUpdated||o||(t=void 0),this._$AL.set(e,t)),r===!0&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[r,s]of this._$Ep)this[r]=s;this._$Ep=void 0}let o=this.constructor.elementProperties;if(o.size>0)for(let[r,s]of o){let{wrapped:i}=s,l=this[r];i!==!0||this._$AL.has(r)||l===void 0||this.C(r,void 0,s,l)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(o=>o.hostUpdate?.()),this.update(t)):this._$EM()}catch(o){throw e=!1,this._$EM(),o}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};w.elementStyles=[],w.shadowRootOptions={mode:"open"},w[N("elementProperties")]=new Map,w[N("finalized")]=new Map,mt?.({ReactiveElement:w}),(Z.reactiveElementVersions??=[]).push("2.1.2");var xe=globalThis,He=n=>n,Q=xe.trustedTypes,Te=Q?Q.createPolicy("lit-html",{createHTML:n=>n}):void 0,Ne="$lit$",C=`lit$${Math.random().toFixed(9).slice(2)}$`,Ve="?"+C,ft=`<${Ve}>`,P=document,z=()=>P.createComment(""),B=n=>n===null||typeof n!="object"&&typeof n!="function",$e=Array.isArray,_t=n=>$e(n)||typeof n?.[Symbol.iterator]=="function",fe=`[ 	
\f\r]`,V=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Oe=/-->/g,De=/>/g,k=RegExp(`>|${fe}(?:([^\\s"'>=/]+)(${fe}*=${fe}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Ie=/'/g,Ue=/"/g,ze=/^(?:script|style|textarea|title)$/i,we=n=>(e,...t)=>({_$litType$:n,strings:e,values:t}),f=we(1),Be=we(2),eo=we(3),M=Symbol.for("lit-noChange"),u=Symbol.for("lit-nothing"),Fe=new WeakMap,E=P.createTreeWalker(P,129);function Ke(n,e){if(!$e(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return Te!==void 0?Te.createHTML(e):e}var gt=(n,e)=>{let t=n.length-1,o=[],r,s=e===2?"<svg>":e===3?"<math>":"",i=V;for(let l=0;l<t;l++){let a=n[l],p,m,h=-1,g=0;for(;g<a.length&&(i.lastIndex=g,m=i.exec(a),m!==null);)g=i.lastIndex,i===V?m[1]==="!--"?i=Oe:m[1]!==void 0?i=De:m[2]!==void 0?(ze.test(m[2])&&(r=RegExp("</"+m[2],"g")),i=k):m[3]!==void 0&&(i=k):i===k?m[0]===">"?(i=r??V,h=-1):m[1]===void 0?h=-2:(h=i.lastIndex-m[2].length,p=m[1],i=m[3]===void 0?k:m[3]==='"'?Ue:Ie):i===Ue||i===Ie?i=k:i===Oe||i===De?i=V:(i=k,r=void 0);let x=i===k&&n[l+1].startsWith("/>")?" ":"";s+=i===V?a+ft:h>=0?(o.push(p),a.slice(0,h)+Ne+a.slice(h)+C+x):a+C+(h===-2?l:x)}return[Ke(n,s+(n[t]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),o]},K=class n{constructor({strings:e,_$litType$:t},o){let r;this.parts=[];let s=0,i=0,l=e.length-1,a=this.parts,[p,m]=gt(e,t);if(this.el=n.createElement(p,o),E.currentNode=this.el.content,t===2||t===3){let h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;(r=E.nextNode())!==null&&a.length<l;){if(r.nodeType===1){if(r.hasAttributes())for(let h of r.getAttributeNames())if(h.endsWith(Ne)){let g=m[i++],x=r.getAttribute(h).split(C),$=/([.?@])?(.*)/.exec(g);a.push({type:1,index:s,name:$[2],strings:x,ctor:$[1]==="."?ge:$[1]==="?"?ye:$[1]==="@"?be:H}),r.removeAttribute(h)}else h.startsWith(C)&&(a.push({type:6,index:s}),r.removeAttribute(h));if(ze.test(r.tagName)){let h=r.textContent.split(C),g=h.length-1;if(g>0){r.textContent=Q?Q.emptyScript:"";for(let x=0;x<g;x++)r.append(h[x],z()),E.nextNode(),a.push({type:2,index:++s});r.append(h[g],z())}}}else if(r.nodeType===8)if(r.data===Ve)a.push({type:2,index:s});else{let h=-1;for(;(h=r.data.indexOf(C,h+1))!==-1;)a.push({type:7,index:s}),h+=C.length-1}s++}}static createElement(e,t){let o=P.createElement("template");return o.innerHTML=e,o}};function L(n,e,t=n,o){if(e===M)return e;let r=o!==void 0?t._$Co?.[o]:t._$Cl,s=B(e)?void 0:e._$litDirective$;return r?.constructor!==s&&(r?._$AO?.(!1),s===void 0?r=void 0:(r=new s(n),r._$AT(n,t,o)),o!==void 0?(t._$Co??=[])[o]=r:t._$Cl=r),r!==void 0&&(e=L(n,r._$AS(n,e.values),r,o)),e}var _e=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:o}=this._$AD,r=(e?.creationScope??P).importNode(t,!0);E.currentNode=r;let s=E.nextNode(),i=0,l=0,a=o[0];for(;a!==void 0;){if(i===a.index){let p;a.type===2?p=new j(s,s.nextSibling,this,e):a.type===1?p=new a.ctor(s,a.name,a.strings,this,e):a.type===6&&(p=new ve(s,this,e)),this._$AV.push(p),a=o[++l]}i!==a?.index&&(s=E.nextNode(),i++)}return E.currentNode=P,r}p(e){let t=0;for(let o of this._$AV)o!==void 0&&(o.strings!==void 0?(o._$AI(e,o,t),t+=o.strings.length-2):o._$AI(e[t])),t++}},j=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,o,r){this.type=2,this._$AH=u,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=o,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=L(this,e,t),B(e)?e===u||e==null||e===""?(this._$AH!==u&&this._$AR(),this._$AH=u):e!==this._$AH&&e!==M&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):_t(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==u&&B(this._$AH)?this._$AA.nextSibling.data=e:this.T(P.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:o}=e,r=typeof o=="number"?this._$AC(e):(o.el===void 0&&(o.el=K.createElement(Ke(o.h,o.h[0]),this.options)),o);if(this._$AH?._$AD===r)this._$AH.p(t);else{let s=new _e(r,this),i=s.u(this.options);s.p(t),this.T(i),this._$AH=s}}_$AC(e){let t=Fe.get(e.strings);return t===void 0&&Fe.set(e.strings,t=new K(e)),t}k(e){$e(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,o,r=0;for(let s of e)r===t.length?t.push(o=new n(this.O(z()),this.O(z()),this,this.options)):o=t[r],o._$AI(s),r++;r<t.length&&(this._$AR(o&&o._$AB.nextSibling,r),t.length=r)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let o=He(e).nextSibling;He(e).remove(),e=o}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},H=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,o,r,s){this.type=1,this._$AH=u,this._$AN=void 0,this.element=e,this.name=t,this._$AM=r,this.options=s,o.length>2||o[0]!==""||o[1]!==""?(this._$AH=Array(o.length-1).fill(new String),this.strings=o):this._$AH=u}_$AI(e,t=this,o,r){let s=this.strings,i=!1;if(s===void 0)e=L(this,e,t,0),i=!B(e)||e!==this._$AH&&e!==M,i&&(this._$AH=e);else{let l=e,a,p;for(e=s[0],a=0;a<s.length-1;a++)p=L(this,l[o+a],t,a),p===M&&(p=this._$AH[a]),i||=!B(p)||p!==this._$AH[a],p===u?e=u:e!==u&&(e+=(p??"")+s[a+1]),this._$AH[a]=p}i&&!r&&this.j(e)}j(e){e===u?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},ge=class extends H{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===u?void 0:e}},ye=class extends H{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==u)}},be=class extends H{constructor(e,t,o,r,s){super(e,t,o,r,s),this.type=5}_$AI(e,t=this){if((e=L(this,e,t,0)??u)===M)return;let o=this._$AH,r=e===u&&o!==u||e.capture!==o.capture||e.once!==o.once||e.passive!==o.passive,s=e!==u&&(o===u||r);r&&this.element.removeEventListener(this.name,this,o),s&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},ve=class{constructor(e,t,o){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=o}get _$AU(){return this._$AM._$AU}_$AI(e){L(this,e)}};var yt=xe.litHtmlPolyfillSupport;yt?.(K,j),(xe.litHtmlVersions??=[]).push("3.3.3");var je=(n,e,t)=>{let o=t?.renderBefore??e,r=o._$litPart$;if(r===void 0){let s=t?.renderBefore??null;o._$litPart$=r=new j(e.insertBefore(z(),s),s,void 0,t??{})}return r._$AI(n),r};var Ce=globalThis,v=class extends w{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=je(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return M}};v._$litElement$=!0,v.finalized=!0,Ce.litElementHydrateSupport?.({LitElement:v});var bt=Ce.litElementPolyfillSupport;bt?.({LitElement:v});(Ce.litElementVersions??=[]).push("4.2.2");function vt(n,e,t){return Math.min(Math.max(n,e),t)}function ee(n,e,t){return t<=e?.5:vt((n-e)/(t-e),0,1)}function xt(n,e,t){if(n==null)return"unknown";if(n<e)return"below";if(n>t)return"above";let o=t-e;if(o<=0)return"in_band";let r=(n-e)/o;return r<.25?"cool_edge":r>.75?"warm_edge":"in_band"}function qe(n){let{operative:e,setpoint:t,low:o,high:r}=n;if(o==null||r==null||r<=o)return null;let s=o-1.5,i=r+1.5;return{low:o,high:r,span:r-o,operative:e,setpoint:t,category:n.category??"",verdict:xt(e,o,r),axisLow:s,axisHigh:i,lowFrac:ee(o,s,i),highFrac:ee(r,s,i),operativeFrac:e==null?null:ee(e,s,i),setpointFrac:t==null?null:ee(t,s,i)}}var We={ok:"var(--success-color, #43a047)",warn:"var(--warning-color, #fb8c00)",alert:"var(--error-color, #e53935)",unknown:"var(--disabled-text-color, #9e9e9e)"};function q(n){return We[n]??We.unknown}var $t=[1e3,2e3],wt=[30,40,60,65],Ct=[26,30],At=420,St=[800,1350];function _(n){return typeof n=="number"&&Number.isFinite(n)}function te(n,e){return n&&n.length>=2&&_(n[0])&&_(n[1])&&n[0]<n[1]?[n[0],n[1]]:[e[0],e[1]]}function kt(n,e){if(n&&n.length>=4&&n.slice(0,4).every(_)){let[t,o,r,s]=n;if(t<=o&&o<=r&&r<=s)return[t,o,r,s]}return[e[0],e[1],e[2],e[3]]}function Et(n){if(n?.scheme==="en16798"){let e=_(n.outdoor)?n.outdoor:At,t=te(n.enRise,St);return[e+t[0],e+t[1]]}return te(n?.thresholds,$t)}function Pt(n,e){if(!_(n))return"unknown";let[t,o]=Et(e);return n>=o?"alert":n>=t?"warn":"ok"}function Mt(n,e){if(!_(n))return"unknown";let[t,o,r,s]=kt(e,wt);return n<t||n>=s?"alert":n<o||n>r?"warn":"ok"}function Rt(n){switch(n){case"in_band":return"ok";case"cool_edge":case"warm_edge":return"warn";case"below":case"above":return"alert";default:return"unknown"}}function Lt(n,e){if(!_(n))return"unknown";let[t,o]=te(e,Ct);return n>o?"alert":n>t?"warn":"ok"}var Ht=[10,15];function Tt(n){return 100-95*Math.exp(-(.03353*n**4+.2179*n**2))}function Ot(n,e,t){let[o,r]=te(t,Ht),s=_(e)?e:_(n)?Tt(n):null;return s==null?"unknown":s>=r?"alert":s>=o?"warn":"ok"}var Dt=[.5,1],It=[3,6],Ut=[85,60];function Xe(n){return n<=1?n*100:n}var Ge={unknown:-1,ok:0,warn:1,alert:2};function Ft(n){let e=[];if(_(n.deviationK)){let[t,o]=Dt;e.push(n.deviationK>=o?"alert":n.deviationK>=t?"warn":"ok")}if(_(n.cyclesPerH)){let[t,o]=It;e.push(n.cyclesPerH>=o?"alert":n.cyclesPerH>=t?"warn":"ok")}if(_(n.timeInBand)){let t=Xe(n.timeInBand),[o,r]=Ut;e.push(t<r?"alert":t<o?"warn":"ok")}return e.length?e.reduce((t,o)=>Ge[o]>Ge[t]?o:t,"ok"):"unknown"}function Ye(n,e){let t=[],o=e?.temperature_scale==="asr_office"?Lt(n.temperature,e.asr_thresholds):Rt(n.comfortVerdict??null);if(t.push({key:"temperature",value:n.temperature,unit:"\xB0C",level:o,color:q(o)}),_(n.humidity)){let s=Mt(n.humidity,e?.humidity_thresholds);t.push({key:"humidity",value:n.humidity,unit:"%",level:s,color:q(s)})}if(_(n.co2)){let s=Pt(n.co2,{scheme:e?.co2_scheme,thresholds:e?.co2_thresholds,outdoor:e?.outdoor_co2});t.push({key:"co2",value:n.co2,unit:"ppm",level:s,color:q(s)})}if(_(n.pmv)||_(n.ppd)){let s=Ot(n.pmv??null,n.ppd??null);t.push({key:"pmv",value:_(n.ppd)?n.ppd:null,unit:"%",level:s,color:q(s)})}let r=n.ca;if(r&&(_(r.deviationK)||_(r.timeInBand)||_(r.cyclesPerH))){let s=Ft(r);t.push({key:"ca",value:_(r.timeInBand)?Xe(r.timeInBand):null,unit:"%",level:s,color:q(s)})}return t}var Ae=["hvac","window","temperature","humidity","co2","ca"],Nt=[12,24,48];function Je(n,e,t){return typeof n=="string"&&e.includes(n)?n:t}function T(n,e){return typeof n=="boolean"?n:e}function Vt(n){return n===!1?new Set:n==null||n===!0?new Set(Ae):Array.isArray(n)?new Set(n.filter(e=>Ae.includes(e))):new Set(Ae)}function zt(n){if(n===!1)return{show:!1,hours:24};if(n===!0||n==null)return{show:!0,hours:24};let e=typeof n.hours=="number"?n.hours:Number(n.hours),t=Nt.includes(e)?e:24;return{show:T(n.show,!0),hours:t}}function Ze(n){let e=n.sections??{},t=n.density?Je(n.density,["comfortable","compact"],"comfortable"):n.compact?"compact":"comfortable";return{entity:n.entity,density:t,controls:Je(n.controls,["dial","buttons","none"],"dial"),history:zt(n.history),chips:Vt(e.chips),shadowPill:T(e.shadow_pill,T(n.show_shadow,!0)),learning:T(e.learning,!0),pmv:T(e.pmv,!0),presets:T(e.presets,!0),temperature_scale:n.temperature_scale,humidity_thresholds:n.humidity_thresholds,co2_scheme:n.co2_scheme,co2_thresholds:n.co2_thresholds}}var Qe={in_band:"In comfort band",cool_edge:"Cool edge of band",warm_edge:"Warm edge of band",below:"Below comfort band",above:"Above comfort band",unknown:"No reading",preheating:"Pre-heating",coasting:"Coasting",window:"Window open",window_auto:"Window (auto)",bypass:"Window detection off",eco:"Eco",comfort:"Comfort",boost:"Boost",away:"Away",failure:"Heating failure",learning:"Learning",shadow:"Shadow active",setpoint:"Setpoint",no_entity:"Select a Poise thermostat entity.",min_left:"min",no_system:"Select the Poise System sensor.",sys_title:"Poise System",demand_on:"Boiler demand",demand_off:"No demand",frost:"Frost override",zones:"zones",heating_n:"heating",flow:"Flow",shed:"shed",shadow_would:"would",update_msg:"New Poise card version available \u2014 reload to update.",reload:"Reload",details:"Show details",temperature:"Temperature",humidity:"Humidity",co2:"CO\u2082",pmv:"Comfort",ca:"Regulation",override_clamped:"Setpoint clamped",compressor_guard:"Compressor guard",mould:"Mould limit",presets:"Presets",air_quality:"Room condition",air_ok:"OK",air_warn:"Elevated",air_alert:"Critical"},Bt={in_band:"Im Komfortband",cool_edge:"Untere Bandkante",warm_edge:"Obere Bandkante",below:"Unter dem Komfortband",above:"\xDCber dem Komfortband",unknown:"Kein Messwert",preheating:"Vorheizen",coasting:"Auslaufen",window:"Fenster offen",window_auto:"Fenster (auto)",bypass:"Fenster-Erkennung aus",eco:"Eco",comfort:"Komfort",boost:"Boost",away:"Abwesend",failure:"Heizausfall",learning:"Lernt",shadow:"Shadow aktiv",setpoint:"Sollwert",no_entity:"Bitte eine Poise-Thermostat-Entit\xE4t w\xE4hlen.",min_left:"Min",no_system:"Bitte den Poise-System-Sensor w\xE4hlen.",sys_title:"Poise System",demand_on:"Kesselbedarf",demand_off:"Kein Bedarf",frost:"Frost-Override",zones:"Zonen",heating_n:"heizen",flow:"Vorlauf",shed:"abgeworfen",shadow_would:"w\xFCrde",update_msg:"Neue Poise-Karten-Version verf\xFCgbar \u2014 zum Aktualisieren neu laden.",reload:"Neu laden",details:"Details anzeigen",temperature:"Temperatur",humidity:"Feuchte",co2:"CO\u2082",pmv:"Behaglichkeit",ca:"Regelg\xFCte",override_clamped:"Sollwert geklemmt",compressor_guard:"Verdichterschutz",mould:"Schimmelgrenze",presets:"Voreinstellungen",air_quality:"Raumzustand",air_ok:"OK",air_warn:"Erh\xF6ht",air_alert:"Kritisch"};function d(n,e){return((n??"en").toLowerCase().startsWith("de")?Bt:Qe)[e]??Qe[e]??e}var Kt=[{value:"hvac",label:"HVAC status"},{value:"window",label:"Window"},{value:"temperature",label:"Temperature"},{value:"humidity",label:"Humidity"},{value:"co2",label:"CO\u2082"},{value:"ca",label:"Regulation (CA)"}],jt=[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"climate"}}},{name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}},{name:"controls",selector:{select:{mode:"dropdown",options:[{value:"dial",label:"Dial (drag)"},{value:"buttons",label:"Buttons (+/\u2212)"},{value:"none",label:"Display only"}]}}},{type:"expandable",name:"history",title:"History",schema:[{name:"show",selector:{boolean:{}}},{name:"hours",selector:{select:{mode:"dropdown",options:[{value:12,label:"12 h"},{value:24,label:"24 h"},{value:48,label:"48 h"}]}}}]},{type:"expandable",name:"sections",title:"Sections",schema:[{name:"chips",selector:{select:{multiple:!0,options:Kt}}},{name:"pmv",selector:{boolean:{}}},{name:"presets",selector:{boolean:{}}},{name:"shadow_pill",selector:{boolean:{}}},{name:"learning",selector:{boolean:{}}}]},{type:"expandable",name:"",title:"Advanced",flatten:!0,schema:[{name:"temperature_scale",selector:{select:{mode:"dropdown",options:[{value:"comfort",label:"Comfort band"},{value:"asr_office",label:"ASR office (\u226426 \xB0C)"}]}}},{name:"co2_scheme",selector:{select:{mode:"dropdown",options:[{value:"uba",label:"UBA (absolute)"},{value:"en16798",label:"EN 16798 (outdoor offset)"}]}}}]}],qt={entity:"Entity",density:"Density",controls:"Controls",history:"History",sections:"Sections",show:"Show graph",hours:"Time span",chips:"Condition chips",pmv:"Comfort (PMV) lamp",presets:"Preset buttons",shadow_pill:"Shadow pill",learning:"Learning bar",temperature_scale:"Temperature scale",co2_scheme:"CO\u2082 scale"},oe=class extends v{setConfig(e){this._config=e}shouldUpdate(e){return e.has("hass")||e.has("_config")}_changed(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e.detail.value}}))}render(){return!this.hass||!this._config?f``:f`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${jt}
      .computeLabel=${e=>qt[e.name]??e.name}
      @value-changed=${this._changed}
    ></ha-form>`}};oe.properties={hass:{},_config:{state:!0}};customElements.get("poise-card-editor")||customElements.define("poise-card-editor",oe);var ne="0.154.0",et=!1;function Wt(){let n=()=>location.reload();"caches"in window?caches.keys().then(e=>Promise.all(e.map(t=>caches.delete(t)))).then(n,n):n()}async function re(n,e){if(!(et||!e?.connection)){et=!0;try{let t=await e.connection.sendMessagePromise({type:"poise/card_version"});if(t?.version&&t.version!==ne){let o=e.locale?.language;n.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:`${d(o,"update_msg")} (${ne} \u2192 ${t.version})`,duration:-1,dismissable:!0,action:{text:d(o,"reload"),action:Wt}},bubbles:!0,composed:!0}))}}catch{}}}function W(n){let e=typeof n=="string"?parseFloat(n):n;return typeof e=="number"&&!Number.isNaN(e)?e:null}var G=class extends v{static getConfigElement(){return document.createElement("poise-system-card-editor")}static getStubConfig(e){return{type:"custom:poise-system-card",entity:Object.keys(e.states).find(o=>o.startsWith("binary_sensor.")&&e.states[o].attributes.zone_count!==void 0)??""}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config=e}getCardSize(){return 2}getGridOptions(){return{columns:12,rows:"auto",min_columns:4,min_rows:4}}updated(){this.hass&&re(this,this.hass)}shouldUpdate(e){if(e.has("_config"))return!0;let t=e.get("hass");return!t||!this._config?.entity?!0:t.states[this._config.entity]!==this.hass.states[this._config.entity]}_moreInfo(){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_onActivateKey(e){(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),this._moreInfo())}render(){let e=this.hass?.locale?.language,t=this._config?.entity,o=t?this.hass.states[t]:void 0;if(!o)return f`<ha-card
        ><div class="empty">${d(e,"no_system")}</div></ha-card
      >`;let r=o.attributes,s=o.state==="on",i=W(r.flow_target),l=W(r.shed_count)??0,a=r.source_grants??{},p=Object.keys(a);return f`<ha-card .header=${d(e,"sys_title")}>
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
    ></ha-form>`}};se.properties={hass:{},_config:{state:!0}};customElements.get("poise-system-card-editor")||customElements.define("poise-system-card-editor",se);customElements.get("poise-system-card")||customElements.define("poise-system-card",G);window.customCards=window.customCards||[];window.customCards.push({type:"poise-system-card",name:"Poise System",preview:!0,description:"Multi-zone boiler demand, flow & load shedding for the Poise hub."});function tt(n,e,t){return Math.min(Math.max(n,e),t)}function ot(n,e,t,o=300,r=90,s=1){let i=[];for(let y of n)y.op!=null&&i.push(y.op),y.sp!=null&&i.push(y.sp);if(e!=null&&i.push(e),t!=null&&i.push(t),i.length===0||n.length===0)return null;let l=Math.min(...i)-s,a=Math.max(...i)+s,p=n[0].t,h=n[n.length-1].t-p||1,g=a-l||1,x=y=>(y-p)/h*o,$=y=>r-(y-l)/g*r,D=y=>n.filter(S=>y(S)!=null).map(S=>`${x(S.t).toFixed(1)},${$(y(S)).toFixed(1)}`).join(" ");return{width:o,height:r,opPath:D(y=>y.op),spPath:D(y=>y.sp),bandTop:t==null?0:tt($(t),0,r),bandBottom:e==null?r:tt($(e),0,r),vMin:l,vMax:a}}var b={min:16,max:28,start:135,sweep:270};function nt(n,e,t){return Math.min(Math.max(n,e),t)}function O(n,e=b){let t=nt((n-e.min)/(e.max-e.min),0,1);return e.start+t*e.sweep}function Gt(n,e=b){let t=n;for(;t<e.start;)t+=360;for(;t>=e.start+360;)t-=360;if(t<=e.start+e.sweep)return t;let o=t-(e.start+e.sweep);return e.start+360-t<o?e.start:e.start+e.sweep}function Xt(n,e=b){let o=(Gt(n,e)-e.start)/e.sweep;return e.min+o*(e.max-e.min)}function A(n,e,t,o){let r=o*Math.PI/180;return{x:n+t*Math.cos(r),y:e+t*Math.sin(r)}}function Se(n,e,t,o,r){if(r<=o)return"";let s=A(n,e,t,o),i=A(n,e,t,r),l=r-o>180?1:0;return`M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${t} ${t} 0 ${l} 1 ${i.x.toFixed(2)} ${i.y.toFixed(2)}`}function rt(n,e,t=b){let o=Math.atan2(e,n)*180/Math.PI;return o<0&&(o+=360),Xt(o,t)}function st(n,e,t,o=b){let r;switch(n){case"ArrowUp":case"ArrowRight":r=e+t;break;case"ArrowDown":case"ArrowLeft":r=e-t;break;case"PageUp":r=e+t*5;break;case"PageDown":r=e-t*5;break;case"Home":r=o.min;break;case"End":r=o.max;break;default:return null}return Math.round(nt(r,o.min,o.max)/t)*t}function it(n){return{eco:"mdi:leaf",boost:"mdi:rocket-launch",away:"mdi:home-export-outline",comfort:"mdi:sofa"}[n]??"mdi:tune"}function c(n){let e=typeof n=="string"?parseFloat(n):n;return typeof e=="number"&&!Number.isNaN(e)?e:null}var X=class extends v{constructor(){super(...arguments);this._history=[];this._histFor=null;this._dragging=!1;this._pending=null;this._dialCfg=b}static getConfigElement(){return document.createElement("poise-card-editor")}static getStubConfig(t){return{type:"custom:poise-card",entity:Object.keys(t.states).find(r=>r.startsWith("climate.")&&t.states[r].attributes.comfort_low!==void 0)??"",show_shadow:!0}}setConfig(t){if(!t)throw new Error("Invalid configuration");if(t.entity&&!t.entity.startsWith("climate."))throw new Error("Poise card: entity must be a climate entity");this._config={show_shadow:!0,...t},this._r=Ze(this._config)}getCardSize(){return 4}getGridOptions(){return this._r?.density==="compact"?{columns:6,rows:"auto",min_columns:4,min_rows:6}:{columns:12,rows:"auto",min_columns:6,min_rows:9}}shouldUpdate(t){if(this._dragging||t.has("_config"))return!0;let o=t.get("hass");return!o||!this._config?.entity?!0:o.states[this._config.entity]!==this.hass.states[this._config.entity]}_setpoint(t){let o=this._config.entity;if(!o||!this.hass)return;let r=this.hass.states[o];if(!r)return;let s=c(r.attributes.target_temperature_step)??.5,i=c(r.attributes.heat_sp)??c(r.attributes.temperature)??21;this.hass.callService("climate","set_temperature",{entity_id:o,temperature:Math.round((i+t*s)*10)/10})}updated(){this.hass&&re(this,this.hass);let t=this._config?.entity;t&&this.hass&&this._r?.history.show&&this._histFor!==t&&(this._histFor=t,this._loadHistory(t))}async _loadHistory(t){if(!this.hass.connection)return;let o=this._r?.history.hours??24,r=new Date,s=new Date(r.getTime()-o*3600*1e3);try{let l=(await this.hass.connection.sendMessagePromise({type:"history/history_during_period",start_time:s.toISOString(),end_time:r.toISOString(),entity_ids:[t],minimal_response:!1,no_attributes:!1}))?.[t]??[],a={},p=[];for(let m of l){m.a&&(a={...a,...m.a});let h=(c(m.lu)??c(m.lc)??0)*1e3;p.push({t:h,op:c(a.operative_temperature)??c(a.current_temperature),sp:c(a.heat_sp)??c(a.temperature)})}this._history=p,this.requestUpdate()}catch{}}_moreInfo(){this._config.entity&&this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_chart(t,o){let r=ot(this._history,t,o,300,80);return r?f`<svg
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
    </svg>`:u}render(){let t=this.hass?.locale?.language,o=this._config?.entity,r=o?this.hass.states[o]:void 0;if(!r)return f`<ha-card
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
    </ha-card>`}_dial(t,o){let r=c(t.operative_temperature)??c(t.current_temperature),s=c(t.heat_sp)??c(t.temperature),i={min:c(t.min_temp)??b.min,max:c(t.max_temp)??b.max,start:b.start,sweep:b.sweep};this._dialCfg=i.max>i.min?i:b;let l=this._pending??s??r??this._dialCfg.min,a=c(t.comfort_low),p=c(t.comfort_high),m=100,h=100,g=80,x=Se(m,h,g,b.start,b.start+b.sweep),$=a!=null&&p!=null?Se(m,h,g,O(Math.min(a,p),this._dialCfg),O(Math.max(a,p),this._dialCfg)):"",D=String(t.hvac_action??""),y=D==="heating"?"heat":D==="cooling"?"cool":"",S=A(m,h,g,O(l,this._dialCfg)),ie=r!=null?A(m,h,g,O(r,this._dialCfg)):null,R=c(t.mould_floor),I=R!=null&&R>this._dialCfg.min&&R<this._dialCfg.max,ae=I?O(R,this._dialCfg):0,le=I?A(m,h,g-9,ae):null,ce=I?A(m,h,g+9,ae):null,de=I?A(m,h,g+17,ae):null,pe=this._r.controls==="dial";return f`<div class="dialwrap">
      <svg
        class="dial ${pe?"":"ro"}"
        viewBox="0 0 200 200"
        role=${pe?"slider":"img"}
        tabindex=${pe?0:-1}
        aria-label=${d(o,"setpoint")}
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
        <path class="bandarc" d=${$}></path>
        ${I&&le&&ce&&de?Be`<line class="mould" x1=${le.x.toFixed(1)} y1=${le.y.toFixed(1)} x2=${ce.x.toFixed(1)} y2=${ce.y.toFixed(1)}><title>${d(o,"mould")} ${R.toFixed(1)}°</title></line><text class="mlbl" x=${de.x.toFixed(1)} y=${de.y.toFixed(1)}>${R.toFixed(0)}°</text>`:u}
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
          aria-label=${d(o,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          <div class="op">${r!=null?r.toFixed(1):"\u2014"}<span>°C</span></div>
          <div class="soll">${d(o,"setpoint")} <b>${l.toFixed(1)}°</b></div>
        </div>
      </div>
    </div>`}_fromPointer(t,o){let r=o.getBoundingClientRect();if(!r.width||!this._config.entity)return;let s=(t.clientX-r.left)/r.width*200-100,i=(t.clientY-r.top)/r.height*200-100,l=c(this.hass.states[this._config.entity]?.attributes.target_temperature_step)??.5;this._pending=Math.round(rt(s,i,this._dialCfg)/l)*l,this.requestUpdate()}_onDown(t){if(!this._config.entity||this._r.controls!=="dial")return;t.preventDefault();let o=t.currentTarget;o.setPointerCapture(t.pointerId),this._dragging=!0,this._fromPointer(t,o)}_onMove(t){this._dragging&&this._fromPointer(t,t.currentTarget)}_onUp(){if(!this._dragging)return;this._dragging=!1;let t=this._pending;this._pending=null,t!=null&&this._config.entity&&this.hass.callService("climate","set_temperature",{entity_id:this._config.entity,temperature:t}),this.requestUpdate()}_onKey(t){let o=this._config.entity;if(!o||this._r.controls!=="dial")return;let r=this.hass.states[o];if(!r)return;let s=c(r.attributes.target_temperature_step)??.5,i=c(r.attributes.heat_sp)??c(r.attributes.temperature)??this._dialCfg.min,l=st(t.key,i,s,this._dialCfg);l!=null&&(t.preventDefault(),this.hass.callService("climate","set_temperature",{entity_id:o,temperature:l}))}_onActivateKey(t){(t.key==="Enter"||t.key===" ")&&(t.preventDefault(),this._moreInfo())}_control(t,o){return f`<div class="ctl">
      <ha-icon-button @click=${()=>this._setpoint(-1)} label="-">
        <ha-icon icon="mdi:minus"></ha-icon>
      </ha-icon-button>
      <div class="sp">
        <span>${d(o,"setpoint")}</span
        ><strong>${t!=null?t.toFixed(1):"\u2014"}°C</strong>
      </div>
      <ha-icon-button @click=${()=>this._setpoint(1)} label="+">
        <ha-icon icon="mdi:plus"></ha-icon>
      </ha-icon-button>
    </div>`}_setPreset(t){let o=this._config.entity;!o||!this.hass||this.hass.callService("climate","set_preset_mode",{entity_id:o,preset_mode:t})}_presets(t,o){if(!this._r.presets)return u;let r=t.preset_modes;if(!Array.isArray(r)||!r.length)return u;let s=t.preset_mode==null?null:String(t.preset_mode);return f`<div class="presets" role="group" aria-label=${d(o,"presets")}>
      ${r.map(i=>{let l=String(i);return f`<button
          class="preset ${s===l?"on":""}"
          aria-pressed=${s===l?"true":"false"}
          @click=${()=>this._setPreset(l)}
        >
          <ha-icon icon=${it(l.toLowerCase())}></ha-icon>
          <span>${d(o,l.toLowerCase())||l}</span>
        </button>`})}
    </div>`}_chips(t,o){let r=this._r,s=[];if(r.chips.has("hvac")){t.preheating&&s.push(this._chip("mdi:fire-circle",d(o,"preheating"),t.minutes_to_comfort,o)),t.coasting&&s.push(this._chip("mdi:coffee",d(o,"coasting"),t.minutes_to_setback,o));let i=t.preset==null?"none":String(t.preset);i!=="none"&&!r.presets&&s.push(this._chip(it(i),d(o,i)||i)),t.heating_failure&&s.push(this._chip("mdi:alert",d(o,"failure"))),t.override_clamped&&s.push(this._chip("mdi:arrow-collapse-vertical",d(o,"override_clamped"))),t.mode_nudge_blocked&&s.push(this._chip("mdi:timer-sand",`${d(o,"compressor_guard")}: ${t.mode_nudge_blocked}`));let l=t.binding_lower_cause;l&&l!=="en16798"&&s.push(this._chip("mdi:shield-alert",String(l)))}return r.chips.has("window")&&(t.window_open&&s.push(this._chip("mdi:window-open",d(o,t.window_auto_detected?"window_auto":"window"))),t.window_bypass&&s.push(this._chip("mdi:window-closed-variant",d(o,"bypass")))),s.length?f`<div
          class="chips"
          role="button"
          tabindex="0"
          aria-label=${d(o,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          ${s}
        </div>`:u}_chip(t,o,r,s){let i=c(r);return f`<div class="chip">
      <ha-icon icon=${t}></ha-icon><span>${o}</span>
      ${i!=null?f`<em>${Math.round(i)} ${d(s,"min_left")}</em>`:u}
    </div>`}_monitor(t,o,r){let s=Ye({temperature:c(t.operative_temperature)??c(t.current_temperature),comfortVerdict:o?.verdict??null,humidity:c(t.humidity)??c(t.current_humidity),co2:c(t.co2)??c(t.carbon_dioxide),pmv:c(t.pmv),ppd:c(t.ppd),ca:{deviationK:c(t.ca_deviation_k),timeInBand:c(t.ca_time_in_band),cyclesPerH:c(t.ca_cycles_per_h)}},{temperature_scale:this._config.temperature_scale,humidity_thresholds:this._config.humidity_thresholds,co2_scheme:this._config.co2_scheme,co2_thresholds:this._config.co2_thresholds,outdoor_co2:c(t.outdoor_co2)}),i=this._r,l=s.filter(a=>a.key==="pmv"?i.pmv:i.chips.has(a.key));return l.length?f`<div
      class="monitor"
      role="group"
      aria-label=${d(r,"air_quality")}
    >
      ${l.map(a=>this._lamp(a,r))}
    </div>`:u}_lamp(t,o){let r=d(o,t.key),s=d(o,t.level==="unknown"?"unknown":"air_"+t.level),i="\u2014";t.value!=null&&(i=t.key==="temperature"?t.value.toFixed(1):String(Math.round(t.value)));let l=`${r}: ${i} ${t.unit} \u2014 ${s}`;return f`<div class="lamp" title=${l} aria-label=${l}>
      <span class="dot" style="background:${t.color}"></span>
      <span class="lk">${r}</span>
      <span class="lv">${i}<small>${t.unit}</small></span>
    </div>`}_learn(t,o){let r=c(t.confidence),s=this._r.learning&&r!=null,i=this._r.shadowPill&&(t.mpc_active||t.tpi_active||t.pi_active);if(!s&&!i)return u;let l=c(t.pi_setpoint),a=c(t.mpc_setpoint),p=t.tpi_active?`TPI ${Math.round(c(t.tpi_valve_percent)??0)}%`:t.pi_active&&l!=null?`PI ${l.toFixed(1)}\xB0`:t.mpc_active&&a!=null?`MPC ${a.toFixed(1)}\xB0`:"";return f`<div class="learn">
      ${s?f`<div class="bar">
            <i style="width:${((r??0)*100).toFixed(0)}%"></i>
          </div>
          <span>${d(o,"learning")} ${((r??0)*100).toFixed(0)}%</span>`:u}
      ${i?f`<div class="pill">
            ${d(o,"shadow")}${p?f` · ${p}`:u}
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
  `;window.customCards=window.customCards||[];window.customCards.push({type:"poise-card",name:"Poise Thermostat",preview:!0,description:"EN-16798 comfort band, operative temperature & shadow state for Poise."});customElements.get("poise-card")||customElements.define("poise-card",X);console.info(`%c POISE-CARD ${ne} `,"background:#2196f3;color:#fff");export{X as PoiseCard};
